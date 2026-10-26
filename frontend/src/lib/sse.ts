/** Incremental server-sent-events parser. Feed it the growing buffer; it returns complete events
 *  and the unfinished remainder (chunks from fetch() can split an event anywhere). */
export function parseSSE<T = unknown>(buffer: string): { events: T[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: T[] = [];
  for (const block of blocks) {
    const data = block
      .split("\n")
      .filter((l) => l.startsWith("data:"))
      .map((l) => l.slice(5).replace(/^ /, ""))
      .join("\n");
    if (!data) continue;
    try {
      events.push(JSON.parse(data) as T);
    } catch {
      /* ignore malformed event, keep the stream alive */
    }
  }
  return { events, rest };
}
