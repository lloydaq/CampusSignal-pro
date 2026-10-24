/** Instants shown in the college's time zone (Rules R-4.6, NFR-I18N-001). */
export function formatDateTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone }).format(new Date(iso));
}

function zonedParts(date: Date, timeZone: string): Record<string, number> {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(date);
  const out: Record<string, number> = {};
  for (const part of parts) if (part.type !== "literal") out[part.type] = Number(part.value);
  return out;
}

/** The UTC offset (ms) of `timeZone` at the instant `utcMs`. */
function offsetAt(utcMs: number, timeZone: string): number {
  const p = zonedParts(new Date(utcMs), timeZone);
  return Date.UTC(p.year!, p.month! - 1, p.day, p.hour, p.minute, p.second) - utcMs;
}

/**
 * A `<input type="datetime-local">` value ("2026-10-24T17:30") read as a wall-clock time in the
 * college's time zone, as an ISO instant. The browser's own zone plays no part.
 */
export function zonedInputToIso(value: string, timeZone: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("Expected YYYY-MM-DDTHH:mm");
  const [, y, mo, d, h, mi] = match.map(Number);
  const wall = Date.UTC(y!, mo! - 1, d, h, mi);
  // Two passes settle the offset across a DST change.
  let utc = wall - offsetAt(wall, timeZone);
  utc = wall - offsetAt(utc, timeZone);
  return new Date(utc).toISOString();
}

/** The inverse: an ISO instant as a datetime-local value in the college's time zone. */
export function isoToZonedInput(iso: string, timeZone: string): string {
  const p = zonedParts(new Date(iso), timeZone);
  const pad = (n: number | undefined) => String(n).padStart(2, "0");
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`;
}
