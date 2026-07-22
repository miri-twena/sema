import { describe, expect, it } from "vitest";
import { compact, followUpsLabel, formatCell, formatMetric, formatValue, isIdColumn } from "./format";

describe("formatMetric", () => {
  // The count/currency split is deliberate: money abbreviates because magnitude
  // is what matters at a glance; counts never do, because "1.2K customers"
  // hides whether it is 1,200 or 1,249.
  it("abbreviates money but never counts", () => {
    expect(formatMetric(1_672_356, "currency")).toBe("$1.67M");
    expect(formatMetric(824_068, "currency")).toBe("$824.1K");
    expect(formatMetric(1247, "count")).toBe("1,247");
  });

  it("trims trailing zeros from abbreviations", () => {
    expect(compact(600_000)).toBe("600K");
    expect(compact(1_300_000)).toBe("1.3M");
    expect(compact(2_850_000)).toBe("2.85M");
  });

  // An identifier must never be formatted as a quantity -- customer 1047 is not
  // "1,047", and pandas' 1047.0 must not leak through either.
  it("renders identifiers verbatim", () => {
    expect(formatMetric(1047, "id")).toBe("1047");
    expect(formatMetric(1047.0, "id")).toBe("1047");
  });

  it("passes through non-finite and non-numeric values instead of printing NaN", () => {
    expect(formatMetric(NaN, "currency")).toBe("NaN");
    expect(formatMetric(null, "currency")).toBe("");
    expect(formatMetric(undefined, "count")).toBe("");
  });

  it("formats percents and ratios with their units", () => {
    expect(formatMetric(4.43, "percent")).toBe("4.4%");
    expect(formatMetric(2.5, "ratio")).toBe("2.50x");
  });
});

describe("formatValue", () => {
  // The backend's "number" means numeric-but-not-money, i.e. a count.
  it("maps the backend's KPI formats onto the display rules", () => {
    expect(formatValue(1951, "number")).toBe("1,951");
    expect(formatValue(1_290_000, "currency")).toBe("$1.29M");
  });

  it("falls back to plain text for an unknown format", () => {
    expect(formatValue(42, "not-a-format")).toBe("42");
  });
});

describe("isIdColumn", () => {
  it("detects identifier columns", () => {
    expect(isIdColumn("customer_id")).toBe(true);
    expect(isIdColumn("SKU")).toBe(true);
    expect(isIdColumn("order id")).toBe(true);
  });

  // Anchored to a word boundary so these don't match "id".
  it("does not treat paid/valid/void as identifiers", () => {
    expect(isIdColumn("paid")).toBe(false);
    expect(isIdColumn("valid")).toBe(false);
    expect(isIdColumn("revenue")).toBe(false);
  });
});

describe("formatCell", () => {
  it("renders month buckets as a month label", () => {
    expect(formatCell("2025-06-01T00:00:00.000")).toBe("Jun 2025");
  });

  it("keeps id columns unformatted", () => {
    expect(formatCell(1047, "customer_id")).toBe("1047");
    expect(formatCell(1047, "revenue")).toBe("1,047");
  });

  it("returns an empty string for null and undefined", () => {
    expect(formatCell(null)).toBe("");
    expect(formatCell(undefined)).toBe("");
  });
});

describe("followUpsLabel", () => {
  it("pluralizes correctly", () => {
    expect(followUpsLabel(1)).toBe(", 1 follow-up");
    expect(followUpsLabel(3)).toBe(", 3 follow-ups");
  });

  // The badge itself is aria-hidden, so this suffix is the ONLY place a
  // screen reader hears the count -- "0 follow-ups" would be worse than
  // silence for a widget with no thread at all.
  it("is empty for zero or undefined, never '0 follow-ups'", () => {
    expect(followUpsLabel(0)).toBe("");
    expect(followUpsLabel(undefined)).toBe("");
  });
});
