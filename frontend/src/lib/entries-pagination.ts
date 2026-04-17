export function mergePage<T extends { id: string }>(prev: T[], next: T[]): T[] {
  const seen = new Set(prev.map((x) => x.id));
  const extras = next.filter((x) => !seen.has(x.id));
  return [...prev, ...extras];
}

export function hasMore(loaded: number, total: number): boolean {
  return loaded < total;
}
