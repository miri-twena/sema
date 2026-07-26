import { describe, expect, it } from "vitest";
import { mergeEvents, UNDERSTANDING, type ProgressEvent } from "./progress";

function runSql(index: number): ProgressEvent {
  return { stage: "run_sql", index };
}
function runSqlDone(index: number, rows = 10): ProgressEvent {
  return { stage: "run_sql_done", index, rows };
}
function runSqlError(index: number): ProgressEvent {
  return { stage: "run_sql_error", index };
}

describe("mergeEvents", () => {
  it("merges a single successful query into one active stage", () => {
    const stages = mergeEvents([UNDERSTANDING, { stage: "schema" }, runSql(1), runSqlDone(1)], "en");
    expect(stages.map((s) => s.state)).toEqual(["done", "done", "active"]);
    expect(stages.at(-1)?.label).toBe("Fetching data…");
  });

  it("merges run/fail/retry/done of the SAME index into one stage, not four rows", () => {
    const stages = mergeEvents(
      [UNDERSTANDING, runSql(1), runSqlError(1), runSql(1), runSqlDone(1)],
      "en",
    );
    // understanding + ONE merged queries stage -- not five rows.
    expect(stages).toHaveLength(2);
    expect(stages[1].label).toBe("Fetching data…");
  });

  it("shows retrying while a previously-failed index is running again", () => {
    const stages = mergeEvents([runSql(1), runSqlError(1), runSql(1)], "en");
    expect(stages).toHaveLength(1);
    expect(stages[0].state).toBe("retrying");
    expect(stages[0].label).toBe("retrying…");
  });

  it("shows the orange failed state when a query has failed with no retry yet", () => {
    const stages = mergeEvents([runSql(1), runSqlError(1)], "en");
    expect(stages[0].state).toBe("failed");
    expect(stages[0].label).toBe("Couldn't fetch the data");
  });

  it("recovers from failed back to active once the retry succeeds", () => {
    const stages = mergeEvents([runSql(1), runSqlError(1), runSql(1), runSqlDone(1)], "en");
    expect(stages[0].state).toBe("active");
  });

  it("collapses several DIFFERENT queries into one done/total counter, no index or row numbers", () => {
    const stages = mergeEvents(
      [runSql(1), runSqlDone(1, 100), runSql(2), runSqlDone(2, 6), runSql(3)],
      "en",
    );
    expect(stages).toHaveLength(1); // still one merged "queries" stage
    expect(stages[0].label).toBe("Running queries (2/3)");
    expect(stages[0].label).not.toMatch(/\d+ rows/);
    expect(stages[0].state).toBe("active");
  });

  it("keeps non-query stages (schema/semantic/writing) as separate settled entries", () => {
    const stages = mergeEvents(
      [{ stage: "semantic" }, { stage: "schema" }, runSql(1), runSqlDone(1), { stage: "writing" }],
      "en",
    );
    expect(stages.map((s) => s.state)).toEqual(["done", "done", "done", "active"]);
    expect(stages.at(-1)?.label).toBe("Preparing the answer");
  });

  it("merges consecutive repeats of the SAME plain stage into one entry", () => {
    const stages = mergeEvents([{ stage: "tool" }, { stage: "tool" }, { stage: "tool" }], "en");
    expect(stages).toHaveLength(1);
  });

  it("only the last entry can be active -- every earlier one settles to done", () => {
    const stages = mergeEvents(
      [UNDERSTANDING, { stage: "semantic" }, { stage: "schema" }, runSql(1), runSqlDone(1)],
      "en",
    );
    expect(stages.slice(0, -1).every((s) => s.state === "done")).toBe(true);
  });

  it("renders Hebrew labels for Hebrew lang, with the same merge behavior", () => {
    const stages = mergeEvents([runSql(1), runSqlError(1), runSql(1)], "he");
    expect(stages[0].state).toBe("retrying");
    expect(stages[0].label).toBe("מנסה שוב…");
  });

  it("treats a missing index as index 1 (single-query default)", () => {
    const stages = mergeEvents([{ stage: "run_sql" }, { stage: "run_sql_done", rows: 3 }], "en");
    expect(stages).toHaveLength(1);
    expect(stages[0].label).toBe("Fetching data…");
  });
});
