import { afterEach, describe, expect, it, vi } from "vitest";
import {
  barVisualState,
  HIGHLIGHT_ANNOTATION,
  highlightPoint,
  LINE_LABEL_DENSITY_THRESHOLD,
  lineLabelIndices,
  matchesHighlight,
  niceAxis,
  periodSubtitle,
  pivot,
  prefersReducedMotion,
  tooltipContent,
  xAxisTickStyle,
} from "./chart";
import { CHART_PALETTE, CHART_PALETTE_TEXT } from "./tokens";

describe("pivot", () => {
  it("turns long rows into one wide row per x value, one column per series", () => {
    const rows = [
      { month: "2026-01-01", channel: "Email", revenue: 100 },
      { month: "2026-01-01", channel: "Ads", revenue: 50 },
      { month: "2026-02-01", channel: "Email", revenue: 120 },
    ];
    const { data, series } = pivot(rows, "month", "channel", "revenue");
    expect(series).toEqual(["Email", "Ads"]);
    expect(data).toEqual([
      { month: "2026-01-01", Email: 100, Ads: 50 },
      { month: "2026-02-01", Email: 120 },
    ]);
  });
});

describe("periodSubtitle", () => {
  it("formats the first/last row's date column as a readable range", () => {
    const rows = [{ month: "2025-01-01" }, { month: "2025-06-01" }, { month: "2026-06-01" }];
    expect(periodSubtitle(rows, "month")).toBe("Jan 2025 – Jun 2026");
  });

  it("returns null for a single row (no range to show)", () => {
    expect(periodSubtitle([{ month: "2026-01-01" }], "month")).toBeNull();
  });

  it("returns null when the same date appears at both ends", () => {
    expect(periodSubtitle([{ month: "2026-01-01" }, { month: "2026-01-01" }], "month")).toBeNull();
  });

  it("returns null for a non-date x column -- never invents a period", () => {
    const rows = [{ category: "Electronics" }, { category: "Beauty" }];
    expect(periodSubtitle(rows, "category")).toBeNull();
  });

  it("returns null when x is missing or there are no rows", () => {
    expect(periodSubtitle([{ a: 1 }], undefined)).toBeNull();
    expect(periodSubtitle([], "month")).toBeNull();
  });
});

describe("xAxisTickStyle", () => {
  it("keeps horizontal labels for a small number of categories", () => {
    expect(xAxisTickStyle(4)).toEqual({ angle: 0, textAnchor: "middle", height: 24 });
  });

  it("angles labels once there are more than 8 categories (e.g. 13 months)", () => {
    const style = xAxisTickStyle(13);
    expect(style.angle).toBeLessThan(0);
    expect(style.textAnchor).toBe("end");
  });
});

describe("highlightPoint", () => {
  const rows = [
    { month: "2026-01-01", revenue: 100 },
    { month: "2026-03-01", revenue: 60 },
    { month: "2026-06-01", revenue: 150 },
  ];

  it("finds the real row matching the backend's highlight_x", () => {
    expect(highlightPoint(rows, "month", "revenue", "2026-03-01")).toEqual({
      x: "2026-03-01",
      y: 60,
    });
  });

  it("returns null when highlight_x isn't in the data -- never invents a point", () => {
    expect(highlightPoint(rows, "month", "revenue", "2026-12-01")).toBeNull();
  });

  it("returns null when highlight_x is absent", () => {
    expect(highlightPoint(rows, "month", "revenue", undefined)).toBeNull();
  });

  it("returns null when x or y column names are missing", () => {
    expect(highlightPoint(rows, null, "revenue", "2026-03-01")).toBeNull();
  });
});

describe("tooltipContent", () => {
  const fmt = (v: unknown) => `$${v}`;

  it("expands a short axis-style date label to the full month/year form", () => {
    const { label } = tooltipContent("2026-06-01", [], fmt);
    expect(label).toBe("Jun 2026");
  });

  it("passes through a non-date label unchanged", () => {
    const { label } = tooltipContent("Electronics", [], fmt);
    expect(label).toBe("Electronics");
  });

  it("formats every series entry with the given formatter", () => {
    const { entries } = tooltipContent("2026-06-01", [
      { name: "Email", value: 120, color: "#7C8CFF" },
      { dataKey: "Ads", value: 80, color: "#7EE6C3" },
    ], fmt);
    expect(entries).toEqual([
      { name: "Email", value: "$120", color: "#7C8CFF" },
      { name: "Ads", value: "$80", color: "#7EE6C3" },
    ]);
  });

  it("returns no entries for an empty/undefined payload", () => {
    expect(tooltipContent("x", undefined, fmt).entries).toEqual([]);
  });
});

describe("niceAxis", () => {
  it("rounds 3,381 up to a 4,000 domain with 1,000-spaced ticks (the answer-screen spec example)", () => {
    expect(niceAxis(3381)).toEqual({ max: 4000, ticks: [0, 1000, 2000, 3000, 4000] });
  });

  it("rounds a small value up to the nearest nice step", () => {
    expect(niceAxis(42)).toEqual({ max: 80, ticks: [0, 20, 40, 60, 80] });
  });

  it("handles zero/negative input without dividing by zero", () => {
    expect(niceAxis(0)).toEqual({ max: 0, ticks: [0] });
    expect(niceAxis(-5)).toEqual({ max: 0, ticks: [0] });
  });
});

describe("matchesHighlight", () => {
  it("matches by loose string equality", () => {
    expect(matchesHighlight("Accessories", "Accessories")).toBe(true);
    expect(matchesHighlight(2026, "2026")).toBe(true);
  });

  it("is false for a value not present, and silently false for no highlight at all", () => {
    expect(matchesHighlight("Accessories", "Apparel")).toBe(false);
    expect(matchesHighlight("Accessories", undefined)).toBe(false);
    expect(matchesHighlight("Accessories", null)).toBe(false);
  });
});

describe("HIGHLIGHT_ANNOTATION", () => {
  it("has exactly two lines in both directions, both non-empty", () => {
    for (const dir of ["rtl", "ltr"] as const) {
      expect(HIGHLIGHT_ANNOTATION[dir]).toHaveLength(2);
      for (const line of HIGHLIGHT_ANNOTATION[dir]) expect(line.length).toBeGreaterThan(0);
    }
  });
});

describe("barVisualState", () => {
  it("gives every bar the same solid baseline when nothing is highlighted", () => {
    const noneA = barVisualState(false, false);
    const noneB = barVisualState(true, false); // isMatch is meaningless without hasHighlight
    expect(noneA).toEqual(noneB);
    expect(noneA.fill).toBe(CHART_PALETTE[0]);
    expect(noneA.categoryColor).toBe("#475569");
    expect(noneA.valueColor).toBe("#334155");
  });

  it("gives the matched bar full opacity, ink category label, and the text-safe accent", () => {
    const state = barVisualState(true, true);
    expect(state.fill).toBe(CHART_PALETTE[0]);
    expect(state.categoryColor).toBe("#1E293B");
    expect(state.categoryWeight).toBe(600);
    expect(state.valueColor).toBe(CHART_PALETTE_TEXT[0]);
  });

  it("dims every OTHER bar to 24% of the same hue -- never a different color", () => {
    const state = barVisualState(false, true);
    expect(state.fill).toBe(`${CHART_PALETTE[0]}3D`);
    expect(state.categoryColor).toBe("#94A3B8");
    expect(state.valueColor).toBe("#94A3B8");
  });
});

describe("lineLabelIndices", () => {
  it("labels every point at or under the threshold (13 monthly points)", () => {
    const values = Array.from({ length: 13 }, (_, i) => i * 10);
    expect(lineLabelIndices(values)).toEqual(new Set(values.map((_, i) => i)));
  });

  it("labels every point exactly at the threshold", () => {
    const values = Array.from({ length: LINE_LABEL_DENSITY_THRESHOLD }, (_, i) => i);
    expect(lineLabelIndices(values).size).toBe(LINE_LABEL_DENSITY_THRESHOLD);
  });

  it("past the threshold, keeps only first/last/min/max", () => {
    // 20 daily points; min at index 5, max at index 15.
    const values = Array.from({ length: 20 }, () => 50);
    values[5] = 10;
    values[15] = 90;
    expect(lineLabelIndices(values)).toEqual(new Set([0, 19, 5, 15]));
  });

  it("collapses to fewer than 4 indices when first/last coincide with min/max", () => {
    // Strictly increasing: min is index 0 (== first), max is the last index.
    const values = Array.from({ length: 20 }, (_, i) => i);
    expect(lineLabelIndices(values)).toEqual(new Set([0, 19]));
  });
});

describe("prefersReducedMotion", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reflects the OS-level media query", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce") }));
    expect(prefersReducedMotion()).toBe(true);
  });

  it("is false when the query doesn't match", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    expect(prefersReducedMotion()).toBe(false);
  });
});
