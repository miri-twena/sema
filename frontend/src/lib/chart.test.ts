import { afterEach, describe, expect, it, vi } from "vitest";
import {
  highlightPoint,
  periodSubtitle,
  pivot,
  prefersReducedMotion,
  tooltipContent,
  xAxisTickStyle,
} from "./chart";

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
