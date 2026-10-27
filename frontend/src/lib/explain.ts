/** Splits a summary into text and figure segments so figures can be styled.
 *  Mirrors the backend's number grammar closely enough for display; the *checking* happens server-side. */
const FIGURE = /-?\$?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?:%|[KMB])?|-?\$?\d+(?:\.\d+)?(?:%|[KMB])?/g;

export type Segment = { text: string; figure: boolean };

export function segmentFigures(text: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  for (const m of text.matchAll(FIGURE)) {
    const start = m.index ?? 0;
    const before = start > 0 ? text[start - 1] : "";
    if (/[A-Za-z_]/.test(before)) continue;                 // "Q4", "B2": part of a label
    if (start > last) out.push({ text: text.slice(last, start), figure: false });
    out.push({ text: m[0], figure: true });
    last = start + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last), figure: false });
  return out;
}
