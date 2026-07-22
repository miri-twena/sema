import { describe, expect, it } from "vitest";
import { formatSql, highlightLine } from "./sql";

/** Everything except whitespace, so we can assert the formatter only ever
 * reflows layout and never alters the query itself. */
function significant(s: string): string {
  return s.replace(/\s+/g, "");
}

describe("formatSql", () => {
  it("breaks clauses onto their own lines", () => {
    const out = formatSql("select a, b from t where x = 1 order by a");
    expect(out.split("\n").length).toBeGreaterThan(1);
  });

  // THE load-bearing guarantee: the viewer must never be able to show SQL that
  // differs from what actually ran. The formatter reflows whitespace only, and
  // falls back to the original text if any non-whitespace character would
  // change -- so a corrupted render is impossible by construction.
  it.each([
    "select a, b from t where x = 1",
    "SELECT count(*) FROM orders o JOIN customers c ON c.id = o.customer_id",
    "with recent as (select * from orders where created_at > now() - interval '30 days') select * from recent",
    "select case when x > 0 then 'pos' else 'neg' end as sign from t",
    "select 'a string with  spaces and, commas' as s",
    "select * from t -- trailing comment",
    "",
    "not even valid sql ((( ",
  ])("preserves every non-whitespace character: %s", (sql) => {
    expect(significant(formatSql(sql))).toBe(significant(sql));
  });

  it("is idempotent -- formatting twice changes nothing further", () => {
    const once = formatSql("select a,b from t where x=1 group by a");
    expect(formatSql(once)).toBe(once);
  });
});

describe("highlightLine", () => {
  it("splits a line into segments covering the whole input", () => {
    const line = "SELECT count(*) FROM orders";
    const segments = highlightLine(line);
    expect(segments.map((s) => s.text).join("")).toBe(line);
  });

  it("tags keywords distinctly from plain identifiers", () => {
    const segments = highlightLine("SELECT a FROM t");
    const keywords = segments.filter((s) => s.cls === "sql-kw").map((s) => s.text);
    expect(keywords).toEqual(["SELECT", "FROM"]);
    // Identifiers carry no class, so they render as plain text.
    expect(segments.some((s) => s.cls === "" && s.text === "a")).toBe(true);
  });

  it("tags a function call distinctly from a bare identifier", () => {
    const segments = highlightLine("select count(*) from t");
    expect(segments.some((s) => s.cls === "sql-fn" && s.text === "count")).toBe(true);
  });

  it("tags string literals so they can't be mistaken for identifiers", () => {
    const segments = highlightLine("select 'literal' from t");
    expect(segments.some((s) => s.cls === "sql-str")).toBe(true);
  });

  it("handles an empty line without throwing", () => {
    expect(() => highlightLine("")).not.toThrow();
  });
});
