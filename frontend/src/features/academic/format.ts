import type { AttendanceSummary } from "./api";

export const SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** 1 Monday … 7 Sunday, today in the college's time zone. */
export function collegeWeekday(timeZone: string, now: Date = new Date()): number {
  const name = new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone }).format(now);
  return SHORT.indexOf(name) + 1;
}

/** "09:00:00" → "09:00" (24-hour, as timetables are printed). */
export const hhmm = (time: string) => time.slice(0, 5);

/** "92.5%" or an em dash when nothing counts yet (EXCUSED sessions leave the denominator). */
export const percent = (s: AttendanceSummary) => (s.percentage === null ? "—" : `${s.percentage}%`);

/** "Tue, 20 Oct 2026" for a calendar date ("2026-10-20"), with no time-zone shift. */
export function formatDay(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(y!, m! - 1, d)));
}

/** Scores keep up to two decimals and drop trailing zeros: 18.5, 20, 7.25. */
export function formatScore(value: number): string {
  return String(Math.round(value * 100) / 100);
}

/** Today's date ("2026-10-21") in the college's time zone, for date inputs. */
export function collegeToday(timeZone: string, now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}
