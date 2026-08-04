import { describe, expect, it } from "vitest";
import { en } from "./en";
import { he } from "./he";

/** Recursively walk both locale trees and collect every leaf's dotted path
 * plus its type ("string" | "function"). A structural mismatch -- a key
 * present in one language but not the other, or a string in one and a
 * function in the other -- fails here even though TypeScript's structural
 * check on `he: TranslationKeys = {...}` already catches most of this at
 * build time; this is the runtime belt to that compile-time suspenders (and
 * the one place that actually reports every mismatch at once instead of
 * stopping at the first TS error). */
function leafPaths(obj: unknown, prefix = ""): Record<string, "string" | "function"> {
  const out: Record<string, "string" | "function"> = {};
  for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") {
      out[path] = "string";
    } else if (typeof value === "function") {
      out[path] = "function";
    } else if (value && typeof value === "object") {
      Object.assign(out, leafPaths(value, path));
    } else {
      throw new Error(`Unexpected leaf type at ${path}: ${typeof value}`);
    }
  }
  return out;
}

// Keys that are legitimately identical in both languages -- punctuation-only
// placeholders with no linguistic content, not an untranslated copy-paste.
const SAME_IN_BOTH_LANGUAGES = new Set([
  "admin.users.detail.unknownDash", // em-dash placeholder, no linguistic content
  "admin.users.invite.emailPlaceholder", // example email address, not translated
]);

describe("locale parity (en <-> he)", () => {
  const enPaths = leafPaths(en);
  const hePaths = leafPaths(he);

  it("has exactly the same set of keys in both languages", () => {
    const enKeys = Object.keys(enPaths).sort();
    const heKeys = Object.keys(hePaths).sort();
    const missingInHe = enKeys.filter((k) => !heKeys.includes(k));
    const missingInEn = heKeys.filter((k) => !enKeys.includes(k));
    expect(missingInHe, "keys present in en.ts but missing from he.ts").toEqual([]);
    expect(missingInEn, "keys present in he.ts but missing from en.ts").toEqual([]);
  });

  it("every key is the same TYPE (string vs. interpolating function) in both languages", () => {
    const mismatches = Object.keys(enPaths).filter((k) => enPaths[k] !== hePaths[k]);
    expect(mismatches, "keys whose en/he value kind (string vs function) disagree").toEqual([]);
  });

  it("every static (non-function) string differs between en and he and is non-empty", () => {
    for (const [path, kind] of Object.entries(enPaths)) {
      if (kind !== "string") continue;
      const enVal = path.split(".").reduce<any>((o, k) => o[k], en);
      const heVal = path.split(".").reduce<any>((o, k) => o[k], he);
      expect(enVal.length, `${path} (en) should be non-empty`).toBeGreaterThan(0);
      expect(heVal.length, `${path} (he) should be non-empty`).toBeGreaterThan(0);
      if (SAME_IN_BOTH_LANGUAGES.has(path)) continue;
      expect(heVal, `${path} should actually be translated, not copied from en`).not.toBe(enVal);
    }
  });

  it("every interpolating function produces non-empty, distinct output for both languages", () => {
    // Every current function-valued key takes one or more args, each either
    // a number or a string -- probe with one of each, repeated to match the
    // function's own declared arity (Function.length), so a 2-arg function
    // like table.cappedNotice(cap, total) gets two real values instead of
    // (arg, undefined) (covers count-based pluralization branches like
    // criticalAlert(1) vs (2) for single-arg functions, same as before).
    for (const [path, kind] of Object.entries(enPaths)) {
      if (kind !== "function") continue;
      const enFn = path.split(".").reduce<any>((o, k) => o[k], en);
      const heFn = path.split(".").reduce<any>((o, k) => o[k], he);
      const arity = Math.max(enFn.length, heFn.length, 1);
      for (const arg of [1, 5, "X"]) {
        const args = Array(arity).fill(arg);
        const enOut = enFn(...args);
        const heOut = heFn(...args);
        expect(enOut.length, `${path}(${args.map((a) => JSON.stringify(a)).join(", ")}) (en) should be non-empty`).toBeGreaterThan(0);
        expect(heOut.length, `${path}(${args.map((a) => JSON.stringify(a)).join(", ")}) (he) should be non-empty`).toBeGreaterThan(0);
      }
    }
  });
});
