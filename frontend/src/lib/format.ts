/** Locale-aware date formatting helpers.
 *  Tagebuch-Einträge speichern YYYY-MM-DD. Für Anzeige konvertieren wir
 *  in lesbares Deutsch wie "14. April 2026".
 */

const LONG = new Intl.DateTimeFormat("de-DE", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

const SHORT = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

function parse(dateStr: string): Date | null {
  // Accept "YYYY-MM-DD" and also ISO timestamps (backend returns plain date strings).
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

export function formatLong(dateStr: string): string {
  const d = parse(dateStr);
  return d ? LONG.format(d) : dateStr;
}

export function formatShort(dateStr: string): string {
  const d = parse(dateStr);
  return d ? SHORT.format(d) : dateStr;
}
