import { formatDateTime, isoToZonedInput, zonedInputToIso } from "./datetime";

describe("college time zone conversions", () => {
  it("reads a datetime-local value in the college's zone, not the browser's", () => {
    expect(zonedInputToIso("2026-10-24T17:30", "Asia/Kolkata")).toBe("2026-10-24T12:00:00.000Z");
    expect(zonedInputToIso("2026-10-24T17:30", "UTC")).toBe("2026-10-24T17:30:00.000Z");
  });

  it("handles a zone with daylight saving on both sides of the change", () => {
    expect(zonedInputToIso("2026-07-01T09:00", "Europe/London")).toBe("2026-07-01T08:00:00.000Z");
    expect(zonedInputToIso("2026-12-01T09:00", "Europe/London")).toBe("2026-12-01T09:00:00.000Z");
  });

  it("round-trips", () => {
    for (const zone of ["Asia/Kolkata", "America/New_York", "UTC"]) {
      expect(isoToZonedInput(zonedInputToIso("2026-11-15T23:45", zone), zone)).toBe("2026-11-15T23:45");
    }
  });

  it("maps a wall time skipped by a DST change to an instant within the hour", () => {
    // 02:30 on 8 March 2026 doesn't exist in New York (clocks jump from 02:00 to 03:00).
    const instant = Date.parse(zonedInputToIso("2026-03-08T02:30", "America/New_York"));
    expect(Math.abs(instant - Date.parse("2026-03-08T07:00:00Z"))).toBeLessThanOrEqual(60 * 60 * 1000);
  });

  it("rejects anything that isn't a datetime-local value", () => {
    expect(() => zonedInputToIso("tomorrow", "UTC")).toThrow();
  });

  it("formats instants in the college's zone", () => {
    expect(formatDateTime("2026-10-24T12:00:00Z", "Asia/Kolkata")).toMatch(/24 Oct 2026, 5:30\s?pm/i);
  });
});
