/**
 * Convert a stored due_time (seconds or milliseconds) to a local Date.
 *
 * @param ts Unix timestamp in either seconds or milliseconds.
 * @returns The corresponding Date.
 */
export function toDate(ts: number): Date {
  return new Date(ts > 1e11 ? ts : ts * 1000);
}

/** Pad a number to two digits. */
function pad(n: number): string {
  return String(n).padStart(2, '0');
}

/** Format a Date as `YYYY-MM-DD` in local time. */
export function dateKey(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Format a Date as `YYYY-MM-DD HH:mm` in local time. */
export function formatDateTime(ts: number): string {
  const d = toDate(ts);
  return `${dateKey(d)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Format as `HH:mm`. */
export function formatTime(ts: number): string {
  const d = toDate(ts);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Monday-first weekday index (0 = Monday ... 6 = Sunday). */
export function mondayIndex(d: Date): number {
  return (d.getDay() + 6) % 7;
}

/** Add (or subtract) days. */
export function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}
