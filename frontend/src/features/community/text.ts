// http(s) addresses only; a trailing full stop, comma or bracket belongs to the sentence.
const URL = /https?:\/\/[^\s<>"]+/g;
const TRAILING = /[.,;:!?)\]}'"]+$/;

/** Split plain text into text and links (COMMUNITY-001: plain text with auto-linked URLs). */
export function linkify(text: string): ({ text: string } | { href: string })[] {
  const parts: ({ text: string } | { href: string })[] = [];
  let last = 0;
  for (const match of text.matchAll(URL)) {
    const start = match.index;
    const raw = match[0];
    const href = raw.replace(TRAILING, "");
    if (start > last) parts.push({ text: text.slice(last, start) });
    parts.push({ href });
    last = start + href.length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}
