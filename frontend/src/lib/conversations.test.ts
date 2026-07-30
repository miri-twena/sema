import { describe, expect, it } from "vitest";
import type { ChatResponse, ConversationDetail, ConversationSummary } from "./api";
import {
  bucketConversations,
  filterByTitle,
  groupOf,
  previewSplit,
  startOfToday,
  turnsFromDetail,
} from "./conversations";
import { dirOf } from "./rtl";

function detail(messages: ConversationDetail["messages"]): ConversationDetail {
  return { id: "c1", title: "t", pinned: false, archived: false, messages };
}

function answer(over: Partial<ChatResponse> = {}): ChatResponse {
  return {
    answer: "rendered answer",
    kpis: [],
    chart: null,
    table: null,
    actions: [],
    follow_up_questions: [],
    sql_used: null,
    confidence: null,
    evidence: null,
    status: "ok",
    error: null,
    ...over,
  };
}

describe("turnsFromDetail", () => {
  // turnsFromDetail's param type was loosened from ConversationDetail to
  // `{messages}` so a ThreadDetail (drill-down thread transcript, same
  // messages shape, different envelope) can reuse it unchanged -- this pins
  // that a thread-shaped object works with no cast or adapter.
  it("also accepts a thread-shaped object (not just a full ConversationDetail)", () => {
    const threadDetail = {
      id: "thread-1",
      conversation_id: "c1",
      turn_index: 0,
      widget_kind: "kpi" as const,
      widget_title: "Revenue",
      messages: [
        { role: "user" as const, content: "why is this down?", payload: null },
        { role: "assistant" as const, content: "Electronics fell.", payload: null },
      ],
    };
    const { turns } = turnsFromDetail(threadDetail);
    expect(turns).toHaveLength(1);
    expect(turns[0].question).toBe("why is this down?");
    expect(turns[0].response?.answer).toBe("Electronics fell.");
  });

  it("hydrates feedback from the assistant message onto the turn", () => {
    const { turns } = turnsFromDetail(
      detail([
        { role: "user", content: "why?", payload: null, feedback: null },
        {
          role: "assistant",
          content: "text",
          payload: answer(),
          feedback: { rating: "down", comment: "wrong numbers" },
        },
      ]),
    );
    expect(turns[0].feedback).toEqual({ rating: "down", comment: "wrong numbers" });
  });

  it("defaults feedback to null when the assistant message has none", () => {
    const { turns } = turnsFromDetail(
      detail([
        { role: "user", content: "why?", payload: null },
        { role: "assistant", content: "text", payload: answer() },
      ]),
    );
    expect(turns[0].feedback).toBeNull();
  });

  it("uses the stored payload when there is one", () => {
    const { turns } = turnsFromDetail(
      detail([
        { role: "user", content: "why?", payload: null },
        { role: "assistant", content: "text", payload: answer({ answer: "rich" }) },
      ]),
    );
    expect(turns).toHaveLength(1);
    expect(turns[0].response?.answer).toBe("rich");
  });

  // REGRESSION: this shipped. A missing payload became `response: null`, which
  // TurnView treats as "still loading" -- so every restored turn sat on the
  // thinking indicator forever instead of showing the text that WAS stored.
  it("degrades a payload-less answer to text, never to pending", () => {
    const { turns } = turnsFromDetail(
      detail([
        { role: "user", content: "why?", payload: null },
        { role: "assistant", content: "the stored text", payload: null },
      ]),
    );
    expect(turns[0].response).not.toBeNull();
    expect(turns[0].response?.answer).toBe("the stored text");
    expect(turns[0].response?.status).toBe("ok");
  });

  it("leaves a genuinely unanswered question pending", () => {
    const { turns } = turnsFromDetail(detail([{ role: "user", content: "why?", payload: null }]));
    expect(turns[0].response).toBeNull();
  });

  it("carries both roles into history, in order", () => {
    const { history } = turnsFromDetail(
      detail([
        { role: "user", content: "q1", payload: null },
        { role: "assistant", content: "a1", payload: null },
        { role: "user", content: "q2", payload: null },
        { role: "assistant", content: "a2", payload: null },
      ]),
    );
    expect(history.map((m) => m.content)).toEqual(["q1", "a1", "q2", "a2"]);
  });

  it("takes direction from the QUESTION's language", () => {
    const { turns } = turnsFromDetail(
      detail([
        { role: "user", content: "למה ההכנסות ירדו?", payload: null },
        { role: "assistant", content: "English answer body", payload: null },
      ]),
    );
    // The whole turn reads RTL because the question was Hebrew -- an English
    // answer body must not flip it back.
    expect(turns[0].dir).toBe("rtl");
  });
});

describe("time grouping", () => {
  const dayStart = startOfToday(new Date("2026-07-21T09:00:00"));
  const hoursAgo = (h: number) => new Date(dayStart + 9 * 3600_000 - h * 3600_000).toISOString();

  function conv(over: Partial<ConversationSummary>): ConversationSummary {
    return {
      id: "x",
      title: "t",
      pinned: false,
      archived: false,
      created_at: hoursAgo(1),
      updated_at: hoursAgo(1),
      message_count: 2,
      ...over,
    };
  }

  it("puts a pinned chat in Pinned regardless of its age", () => {
    expect(groupOf(conv({ pinned: true, updated_at: hoursAgo(24 * 400) }), dayStart)).toBe("pinned");
  });

  it("buckets by how recently the chat was updated", () => {
    expect(groupOf(conv({ updated_at: hoursAgo(2) }), dayStart)).toBe("today");
    expect(groupOf(conv({ updated_at: hoursAgo(24 * 3) }), dayStart)).toBe("week");
    expect(groupOf(conv({ updated_at: hoursAgo(24 * 30) }), dayStart)).toBe("older");
  });

  // A chat must never vanish from the sidebar because of a bad timestamp.
  it("keeps a chat with an unparseable date, in Older", () => {
    expect(groupOf(conv({ updated_at: "not-a-date" }), dayStart)).toBe("older");
  });

  it("puts every conversation in exactly one bucket", () => {
    const all = [
      conv({ id: "a", pinned: true }),
      conv({ id: "b", updated_at: hoursAgo(1) }),
      conv({ id: "c", updated_at: hoursAgo(24 * 3) }),
      conv({ id: "d", updated_at: hoursAgo(24 * 90) }),
    ];
    const buckets = bucketConversations(all, dayStart);
    const ids = Object.values(buckets).flat().map((c) => c.id);
    expect(ids.sort()).toEqual(["a", "b", "c", "d"]);
  });

  it("preserves the server's order within a bucket", () => {
    const buckets = bucketConversations(
      [
        conv({ id: "first", updated_at: hoursAgo(1) }),
        conv({ id: "second", updated_at: hoursAgo(2) }),
      ],
      dayStart,
    );
    expect(buckets.today.map((c) => c.id)).toEqual(["first", "second"]);
  });
});

describe("previewSplit (Previous 7 days row cap)", () => {
  const items = ["a", "b", "c", "d", "e", "f"];

  it("caps at the default limit of 4 by default", () => {
    const { shown, remaining } = previewSplit(items, false);
    expect(shown).toEqual(["a", "b", "c", "d"]);
    expect(remaining).toBe(2);
  });

  it("shows everything once expanded", () => {
    const { shown, remaining } = previewSplit(items, true);
    expect(shown).toEqual(items);
    expect(remaining).toBe(0);
  });

  it("reports no remainder when the group is already at or under the limit", () => {
    expect(previewSplit(["a", "b"], false).remaining).toBe(0);
    expect(previewSplit(["a", "b", "c", "d"], false).remaining).toBe(0);
  });
});

describe("filterByTitle (sidebar search)", () => {
  function conv(id: string, title: string): ConversationSummary {
    return {
      id,
      title,
      pinned: false,
      archived: false,
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-01T00:00:00Z",
      message_count: 1,
    };
  }

  it("matches case-insensitively, anywhere in the title", () => {
    const all = [conv("a", "Why did Revenue drop?"), conv("b", "Channel mix")];
    expect(filterByTitle(all, "revenue").map((c) => c.id)).toEqual(["a"]);
  });

  it("returns everything, in order, for an empty or blank query", () => {
    const all = [conv("a", "first"), conv("b", "second")];
    expect(filterByTitle(all, "")).toEqual(all);
    expect(filterByTitle(all, "   ")).toEqual(all);
  });

  it("keeps the active conversation in the results when it matches", () => {
    const active = conv("active-id", "Why did revenue drop in March?");
    const all = [conv("a", "unrelated chat"), active];
    const matches = filterByTitle(all, "revenue");
    expect(matches.map((c) => c.id)).toContain("active-id");
  });

  it("matches a Hebrew title the same way", () => {
    const all = [conv("a", "למה ההכנסות ירדו במרץ?"), conv("b", "משהו אחר")];
    expect(filterByTitle(all, "הכנסות").map((c) => c.id)).toEqual(["a"]);
  });
});

describe("sidebar title direction (Hebrew vs English)", () => {
  // The sidebar row uses dirOf(title) -- not the browser's dir="auto" -- so
  // direction is deterministic from the conversation's own stored title,
  // matching how the title itself was derived (first message, no translation).
  it("a conversation titled in Hebrew renders rtl", () => {
    expect(dirOf("למה ההכנסות ירדו במרץ?")).toBe("rtl");
  });

  it("a conversation titled in English renders ltr", () => {
    expect(dirOf("Why did revenue drop in March?")).toBe("ltr");
  });

  it("a manually renamed title still gets a direction from its own text", () => {
    // Renaming doesn't re-run any language detection at write time -- the
    // sidebar just reads whatever string is stored, in whatever language the
    // user typed the rename in.
    expect(dirOf("תקציב Q3")).toBe("rtl");
    expect(dirOf("Q3 budget")).toBe("ltr");
  });
});
