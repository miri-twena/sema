// Relative-time formatting for the admin panel's "last active" column. No date
// library (none is installed, and the app avoids new deps) -- just arithmetic
// on the parsed timestamp.

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;
const MONTH = 30 * DAY;
const YEAR = 365 * DAY;

/** ISO timestamp -> "just now" / "5 minutes ago" / "3 days ago" / "2 months
 * ago". Returns "Never" for null/empty (e.g. an invited user who has never
 * signed in) and the raw string if it can't be parsed. */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "Never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;

  const secs = Math.floor((Date.now() - then) / 1000);
  if (secs < 0) return "just now"; // clock skew -- treat a future stamp as now
  if (secs < 45) return "just now";

  const pick = (value: number, unit: string) =>
    `${value} ${unit}${value === 1 ? "" : "s"} ago`;

  if (secs < HOUR) return pick(Math.round(secs / MINUTE), "minute");
  if (secs < DAY) return pick(Math.round(secs / HOUR), "hour");
  if (secs < WEEK) return pick(Math.round(secs / DAY), "day");
  if (secs < MONTH) return pick(Math.round(secs / WEEK), "week");
  if (secs < YEAR) return pick(Math.round(secs / MONTH), "month");
  return pick(Math.round(secs / YEAR), "year");
}

/** Whole days from now until an ISO timestamp, floored at 0. Used for an
 * invite's "expires in N days". */
export function daysUntil(iso: string | null | undefined): number {
  if (!iso) return 0;
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return 0;
  return Math.max(0, Math.ceil((target - Date.now()) / (DAY * 1000)));
}
