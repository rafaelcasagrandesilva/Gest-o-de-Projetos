export function parseTagsInput(raw: string): string[] {
  return raw
    .split(/[,;]+/)
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean)
    .filter((t, i, arr) => arr.indexOf(t) === i)
    .slice(0, 32);
}

export function formatTagsInput(tags: string[] | null | undefined): string {
  if (!tags?.length) return "";
  return tags.join(", ");
}
