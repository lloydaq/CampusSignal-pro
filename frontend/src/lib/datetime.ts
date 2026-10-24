/** Instants shown in the college's time zone (Rules R-4.6, NFR-I18N-001). */
export function formatDateTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone }).format(new Date(iso));
}
