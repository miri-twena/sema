// Avatar helpers shared by the workspace switcher and the admin panel's user
// rows: initials from a label, and a deterministic pastel colour per seed so a
// given user always gets the same tint without storing one.

/** First letters of the first two words: "Auto Insurance" -> "AI". Falls back
 * to the first character so a single-word label still renders something, and to
 * "?" for an empty label. */
export function initials(label: string): string {
  const words = (label || "").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  return words
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

// Soft [background, foreground] pairs drawn from the SEMA palette tints. Muted
// enough that white/dark initials read cleanly on top.
const AVATAR_TINTS: ReadonlyArray<readonly [string, string]> = [
  ["#EEF0FF", "#5B5F9F"], // lavender (primary)
  ["#E6FBF4", "#1B7A5E"], // mint
  ["#FFF1EC", "#B4552F"], // peach
  ["#EAF6FF", "#2C6E9E"], // sky
  ["#FEF7E0", "#8A6D1B"], // sun
  ["#F3ECFF", "#6B4F9E"], // violet
];

/** Deterministic pastel [bg, fg] for a seed (e.g. an email), so a user's avatar
 * colour is stable across sessions and devices without persisting it. Simple
 * DJB2-style hash, then modulo into the tint list. */
export function pastelFor(seed: string): readonly [string, string] {
  let hash = 5381;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 33 + seed.charCodeAt(i)) >>> 0;
  }
  return AVATAR_TINTS[hash % AVATAR_TINTS.length];
}
