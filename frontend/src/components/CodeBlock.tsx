import { isValidElement, type ReactNode } from "react";
import { CopyableBlock } from "./CopyButton";
import { copyText } from "../lib/clipboard";

/** Flatten a rendered markdown subtree back to its plain text. Code fences
 * contain only strings, so this recovers the source exactly -- no line numbers
 * and no highlighting markup, which is what has to reach the clipboard. */
function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children);
  return "";
}

/**
 * Fenced code block from markdown (SQL, JSON, anything). Forced LTR and
 * bidi-isolated: without this, an RTL answer reorders the code's punctuation
 * -- parens, commas and semicolons drift to the wrong end and the copied query
 * stops being valid SQL.
 */
export function CodeBlock({ children }: { children?: ReactNode }) {
  // Markdown always leaves one trailing newline before the closing fence.
  const code = textOf(children).replace(/\n$/, "");
  return (
    <CopyableBlock
      dir="ltr"
      className="mt-2"
      title="Copy code"
      actions={[{ label: "Copy code", run: () => copyText(code) }]}
    >
      <pre className="sema-code sema-scroll">
        <code>{code}</code>
      </pre>
    </CopyableBlock>
  );
}

/** Inline `code` span -- also LTR-isolated so an identifier or a fragment like
 * `WHERE status = 'completed'` reads correctly mid-Hebrew-sentence. */
export function InlineCode({ children }: { children?: ReactNode }) {
  return (
    <code dir="ltr" className="sema-code-inline">
      {children}
    </code>
  );
}
