// Self-contained, dependency-free SQL formatting + syntax highlighting for the
// read-only "View SQL" viewer. The agent emits standard PostgreSQL SELECTs
// (CTEs, JOINs, window functions), which this handles well; anything unusual
// falls back to the original text (see formatSql), so the viewer can never
// show corrupted SQL.

type TokType = "ws" | "comment" | "str" | "num" | "op" | "punct" | "qid" | "word";

interface Tok {
  t: TokType;
  v: string;
  fn?: boolean; // a word immediately followed by "(" -> a function call
}

export interface Segment {
  cls: string; // "" = default (identifier); else a .sql-* class
  text: string;
}

// Keywords to colorize. Multi-word clauses (GROUP BY, LEFT JOIN) are colored
// word-by-word, so each part is listed individually.
const KEYWORDS = new Set(
  (
    "SELECT FROM WHERE GROUP BY ORDER HAVING LIMIT OFFSET WITH AS ON AND OR NOT IN IS " +
    "NULL LIKE ILIKE BETWEEN JOIN INNER LEFT RIGHT FULL OUTER CROSS UNION ALL EXCEPT " +
    "INTERSECT DISTINCT CASE WHEN THEN ELSE END OVER PARTITION WITHIN ASC DESC EXISTS " +
    "USING VALUES INTERVAL FILTER RETURNING TRUE FALSE DESC ASC INTO"
  ).split(" "),
);

// Clause keywords that begin a new line at the statement level.
const CLAUSE_NEWLINE = new Set([
  "SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "HAVING", "LIMIT",
  "OFFSET", "WITH", "UNION", "UNION ALL", "EXCEPT", "INTERSECT", "RETURNING",
]);

const MULTI_TWO: Record<string, string> = {
  "GROUP BY": "GROUP BY",
  "ORDER BY": "ORDER BY",
  "PARTITION BY": "PARTITION BY",
  "WITHIN GROUP": "WITHIN GROUP",
  "UNION ALL": "UNION ALL",
};

function lex(sql: string): Tok[] {
  const out: Tok[] = [];
  let i = 0;
  const n = sql.length;
  while (i < n) {
    const c = sql[i];
    if (/\s/.test(c)) {
      let j = i + 1;
      while (j < n && /\s/.test(sql[j])) j++;
      out.push({ t: "ws", v: sql.slice(i, j) });
      i = j;
    } else if (c === "-" && sql[i + 1] === "-") {
      let j = i + 2;
      while (j < n && sql[j] !== "\n") j++;
      out.push({ t: "comment", v: sql.slice(i, j) });
      i = j;
    } else if (c === "/" && sql[i + 1] === "*") {
      let j = i + 2;
      while (j < n && !(sql[j] === "*" && sql[j + 1] === "/")) j++;
      j = Math.min(j + 2, n);
      out.push({ t: "comment", v: sql.slice(i, j) });
      i = j;
    } else if (c === "'") {
      let j = i + 1;
      while (j < n) {
        if (sql[j] === "'") {
          if (sql[j + 1] === "'") { j += 2; continue; } // escaped '' quote
          j++;
          break;
        }
        j++;
      }
      out.push({ t: "str", v: sql.slice(i, j) });
      i = j;
    } else if (c === '"') {
      let j = i + 1;
      while (j < n && sql[j] !== '"') j++;
      j = Math.min(j + 1, n);
      out.push({ t: "qid", v: sql.slice(i, j) });
      i = j;
    } else if (/[0-9]/.test(c) || (c === "." && /[0-9]/.test(sql[i + 1] ?? ""))) {
      let j = i + 1;
      while (j < n && /[0-9.eE]/.test(sql[j])) j++;
      out.push({ t: "num", v: sql.slice(i, j) });
      i = j;
    } else if (/[A-Za-z_]/.test(c)) {
      let j = i + 1;
      while (j < n && /[A-Za-z0-9_$]/.test(sql[j])) j++;
      out.push({ t: "word", v: sql.slice(i, j) });
      i = j;
    } else {
      const two = sql.slice(i, i + 2);
      if (["<=", ">=", "<>", "!=", "||", "::"].includes(two)) {
        out.push({ t: "op", v: two });
        i += 2;
      } else if ("()[],;".includes(c)) {
        out.push({ t: "punct", v: c });
        i++;
      } else {
        out.push({ t: "op", v: c });
        i++;
      }
    }
  }
  return out;
}

/** One line of SQL -> colored segments, for rendering. */
export function highlightLine(line: string): Segment[] {
  const toks = lex(line);
  const segs: Segment[] = [];
  for (let i = 0; i < toks.length; i++) {
    const tk = toks[i];
    let cls = "";
    if (tk.t === "comment") cls = "sql-comment";
    else if (tk.t === "str") cls = "sql-str";
    else if (tk.t === "num") cls = "sql-num";
    else if (tk.t === "op") cls = "sql-op";
    else if (tk.t === "punct") cls = "sql-punct";
    else if (tk.t === "word") {
      if (KEYWORDS.has(tk.v.toUpperCase())) cls = "sql-kw";
      else {
        let j = i + 1;
        while (j < toks.length && toks[j].t === "ws") j++;
        cls = toks[j] && toks[j].v === "(" ? "sql-fn" : "";
      }
    }
    segs.push({ cls, text: tk.v });
  }
  return segs;
}

/** Merge two/three-word keywords (GROUP BY, LEFT OUTER JOIN) into single tokens
 * so the formatter can reason about whole clauses. */
function mergeKeywords(sig: Tok[]): Tok[] {
  const out: Tok[] = [];
  for (let i = 0; i < sig.length; i++) {
    const a = sig[i];
    const b = sig[i + 1];
    const A = a.v.toUpperCase();
    const B = b ? b.v.toUpperCase() : "";
    const two = `${A} ${B}`;
    if (b && MULTI_TWO[two]) {
      out.push({ t: "word", v: `${a.v} ${b.v}` });
      i++;
      continue;
    }
    if (["INNER", "LEFT", "RIGHT", "FULL", "CROSS"].includes(A)) {
      const parts = [a.v];
      let j = i + 1;
      if (sig[j] && sig[j].v.toUpperCase() === "OUTER") { parts.push(sig[j].v); j++; }
      if (sig[j] && sig[j].v.toUpperCase() === "JOIN") {
        parts.push(sig[j].v);
        out.push({ t: "word", v: parts.join(" ") });
        i = j;
        continue;
      }
    }
    out.push(a);
  }
  return out;
}

interface Scope {
  indent: number;
  statement: boolean; // clause keywords break onto new lines only here
  clause: string;
  subquery: boolean;
  openIndent: number;
}

function emit(tokens: Tok[]): string {
  const lines: string[] = [];
  let cur = "";
  let prev: Tok | null = null;
  const scope: Scope[] = [{ indent: 0, statement: true, clause: "", subquery: false, openIndent: 0 }];
  const top = () => scope[scope.length - 1];
  const pad = (n: number) => "  ".repeat(Math.max(0, n));
  const nl = (lvl: number) => {
    // A whitespace-only line is never worth emitting -- it would show up as a
    // stray blank (e.g. a clause break right after a line comment already
    // broke). Deliberate blank lines are pushed directly, by the `;` handler.
    if (cur.trim() !== "") lines.push(cur.replace(/\s+$/, ""));
    cur = pad(lvl);
    prev = null; // first token on a line takes no leading space
  };
  const spaceBefore = (tk: Tok): string => {
    if (!prev) return "";
    const pv = prev.v;
    const cv = tk.v;
    if (pv === "(" || pv === ".") return "";
    if (cv === ")" || cv === "," || cv === ";" || cv === ".") return "";
    if (pv === "::" || cv === "::") return "";
    if (cv === "(") return prev.fn ? "" : " ";
    return " ";
  };

  for (let k = 0; k < tokens.length; k++) {
    const tk = tokens[k];
    const up = tk.v.toUpperCase();
    const sc = top();

    if (tk.t === "comment") {
      if (tk.v.startsWith("--")) {
        // A line comment runs to end-of-line, so ANY token emitted after it on
        // the same line would be commented out -- silently changing the query.
        // The whitespace-equality net can't catch that (it ignores newlines),
        // so forcing the break here is what makes line comments safe to reflow.
        cur += spaceBefore(tk) + tk.v;
        // Resume at the indent this line already had (e.g. a SELECT-list item),
        // not the clause indent, so the comment doesn't dedent what follows.
        const lineIndent = Math.floor((/^ */.exec(cur)?.[0].length ?? 0) / 2);
        nl(Math.max(sc.indent, lineIndent));
      } else {
        // Block comment: inline where it sits, or alone on a fresh line.
        cur += cur.trim() === "" ? tk.v : spaceBefore(tk) + tk.v;
        prev = tk;
      }
      continue;
    }

    if (tk.v === ";") {
      // Statement separator. `sql_used` concatenates every query the agent ran,
      // so without this the next SELECT continues the previous line.
      cur += ";";
      scope.length = 1;
      scope[0] = { indent: 0, statement: true, clause: "", subquery: false, openIndent: 0 };
      nl(0);
      lines.push(""); // blank line between statements (\n{3,} collapse tidies up)
      continue;
    }

    if (tk.v === ")") {
      const popped = scope.length > 1 ? scope.pop()! : sc;
      if (popped.subquery) nl(popped.openIndent);
      cur += ")";
      prev = tk;
      continue;
    }
    if (tk.v === "(") {
      const next = tokens[k + 1];
      const isSub = !!next && ["SELECT", "WITH"].includes(next.v.toUpperCase());
      cur += spaceBefore(tk) + "(";
      scope.push(
        isSub
          ? { indent: sc.indent + 1, statement: true, clause: "", subquery: true, openIndent: sc.indent }
          : { indent: sc.indent, statement: false, clause: sc.clause, subquery: false, openIndent: sc.indent },
      );
      prev = tk;
      continue;
    }
    if (sc.statement && CLAUSE_NEWLINE.has(up)) {
      nl(sc.indent);
      cur += tk.v;
      sc.clause = up;
      prev = tk;
      continue;
    }
    if (sc.statement && up.endsWith("JOIN")) {
      nl(sc.indent);
      cur += tk.v;
      sc.clause = "JOIN";
      prev = tk;
      continue;
    }
    if (sc.statement && (up === "AND" || up === "OR") && ["WHERE", "HAVING", "ON", "JOIN"].includes(sc.clause)) {
      nl(sc.indent + 1);
      cur += tk.v;
      prev = tk;
      continue;
    }
    if (up === "ON" && sc.statement) sc.clause = "ON";
    if (tk.v === "," && sc.statement && (sc.clause === "SELECT" || sc.clause === "WITH")) {
      cur += ",";
      // nl() leaves prev=null so the next token starts the line with no leading
      // space -- do NOT set prev to the comma here.
      nl(sc.indent + (sc.clause === "SELECT" ? 1 : 0));
      continue;
    }

    cur += spaceBefore(tk) + tk.v;
    prev = tk;
  }
  if (cur.trim() !== "") lines.push(cur.replace(/\s+$/, ""));
  return lines.join("\n");
}

/** Format SQL for display. Only reflows whitespace -- if the result would drop
 * or alter any non-whitespace character (a formatter bug, or SQL shaped in a
 * way this doesn't handle), the original is returned untouched. */
export function formatSql(raw: string): string {
  const input = (raw ?? "").trim();
  if (!input) return input;
  try {
    const all = lex(input);
    // Comments are kept in the token stream and laid out by emit() -- the agent
    // annotates drill-down SQL, and bailing out on any comment left exactly
    // those queries unformatted.
    const sig = mergeKeywords(all.filter((t) => t.t !== "ws"));
    for (let i = 0; i < sig.length; i++) {
      // A function call is a plain word (not a keyword, not a merged multi-word
      // clause like "WITHIN GROUP") immediately followed by "(".
      const w = sig[i];
      if (w.t === "word" && !KEYWORDS.has(w.v.toUpperCase()) && !w.v.includes(" ")) {
        w.fn = !!sig[i + 1] && sig[i + 1].v === "(";
      }
    }
    const out = emit(sig).replace(/\n{3,}/g, "\n\n").replace(/\s+$/g, "");

    // Safety net 1: identical once all whitespace is removed => nothing lost.
    const bare = (s: string) => s.replace(/\s+/g, "");
    if (bare(out) !== bare(input)) return input;

    // Safety net 2, for line comments only. Net 1 strips newlines, so it cannot
    // tell `a -- c\nFROM t` from `a -- c FROM t` -- yet the second silently
    // comments out FROM t. Re-lex the output and require every `--` comment to
    // be the last token on its line.
    for (const line of out.split("\n")) {
      const toks = lex(line);
      const at = toks.findIndex((t) => t.t === "comment" && t.v.startsWith("--"));
      if (at !== -1 && toks.slice(at + 1).some((t) => t.t !== "ws")) return input;
    }
    return out;
  } catch {
    return input;
  }
}
