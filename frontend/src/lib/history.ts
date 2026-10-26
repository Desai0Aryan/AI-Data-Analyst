const KEY = "verity.history.v1";
export type HistoryItem = { question: string; status: "ok" | "failed" | "cannot_answer"; at: number; rows?: number };

export function loadHistory(): HistoryItem[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(raw) ? raw.slice(0, 12) : [];
  } catch {
    return [];
  }
}

export function pushHistory(items: HistoryItem[], item: HistoryItem): HistoryItem[] {
  const next = [item, ...items.filter((i) => i.question.toLowerCase() !== item.question.toLowerCase())].slice(0, 12);
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* private mode / quota: history is a convenience, never fatal */
  }
  return next;
}

export function clearHistory() {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}
