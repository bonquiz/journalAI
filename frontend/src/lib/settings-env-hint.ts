/**
 * Return a hint string to show under an empty Settings input field when the
 * backend has resolved a value from ENV. Returns null when the DB field is
 * non-empty or when there is no resolved value.
 */
export function envHint(dbValue: string | null | undefined, resolved: string | null | undefined): string | null {
  const db = (dbValue ?? "").trim();
  const res = (resolved ?? "").trim();
  if (db.length > 0) return null;
  if (res.length === 0) return null;
  return res;
}
