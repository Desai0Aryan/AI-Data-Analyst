import { ArrowRight, Clock, ShieldAlert, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { HistoryItem } from "../lib/history";
import type { Meta } from "../lib/types";
import { Kbd, cx } from "./ui";

const CHIPS: { id: string; label: string; kind?: "refusal" | "attack" }[] = [
  { id: "trap_biggest_decline", label: "Biggest revenue decline last quarter" },
  { id: "date_last_quarter_revenue", label: "Revenue last quarter" },
  { id: "join_top_customers", label: "Top 5 customers by revenue" },
  { id: "trap_no_sales_last_quarter", label: "Products with no sales last quarter" },
  { id: "date_quarterly_2025", label: "Quarterly revenue in 2025" },
  { id: "refuse_missing_data", label: "Satisfaction score by product", kind: "refusal" },
  { id: "sec_drop", label: "Drop the orders table", kind: "attack" },
];

export function AskBar({ examples, busy, onAsk, onStop, history, onClearHistory, focusSignal }: {
  examples: Meta["examples"]; busy: boolean; onAsk: (q: string) => void; onStop: () => void;
  history: HistoryItem[]; onClearHistory: () => void; focusSignal: number;
}) {
  const [text, setText] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current?.focus(); input.current?.select(); }, [focusSignal]);

  const submit = (q = text) => {
    const clean = q.trim();
    if (clean.length < 3 || busy) return;
    setText(clean);
    onAsk(clean);
  };
  const byId = new Map(examples.map((e) => [e.id, e.question]));
  const chips = CHIPS.filter((c) => byId.has(c.id));

  return (
    <div>
      <form onSubmit={(e) => { e.preventDefault(); busy ? onStop() : submit(); }} className="flex items-center gap-2 rounded-[14px] border border-line bg-surface p-2 pl-5 transition-colors focus-within:border-signal">
        <label htmlFor="ask" className="sr-only">Ask a question about the data</label>
        <input
          id="ask" ref={input} value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} autoComplete="off" spellCheck={false}
          placeholder="Which products had the biggest revenue decline last quarter?"
          className="min-w-0 flex-1 bg-transparent py-2.5 text-lg outline-none placeholder:text-faint"
        />
        <span className="hidden items-center gap-1 pr-1 text-xs text-faint sm:flex"><Kbd>/</Kbd> to focus</span>
        <button type="submit" disabled={!busy && text.trim().length < 3}
          className={cx("inline-flex min-w-[96px] cursor-pointer items-center justify-center gap-2 rounded-[10px] px-4 py-2.5 text-[15px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40",
            busy ? "border border-line text-text hover:bg-raised" : "bg-signal text-page hover:bg-[#a6b4ff]")}>
          {busy ? <><Square size={14} fill="currentColor" />Stop</> : <>Ask<ArrowRight size={17} /></>}
        </button>
      </form>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="mr-1 text-sm text-faint">Try</span>
        {chips.map((c) => (
          <button key={c.id} disabled={busy} onClick={() => submit(byId.get(c.id)!)}
            className={cx("inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-[13.5px] transition-colors disabled:cursor-not-allowed disabled:opacity-40",
              c.kind === "attack" ? "border-blocked/40 text-blocked hover:bg-blocked/10" : c.kind === "refusal" ? "border-repaired/40 text-repaired hover:bg-repaired/10" : "border-line/80 text-muted hover:border-signal/60 hover:text-text")}>
            {c.kind === "attack" && <ShieldAlert size={14} />}{c.label}
          </button>
        ))}
      </div>

      {history.length > 0 && (
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          <span className="mr-1 inline-flex items-center gap-1 text-sm text-faint"><Clock size={13} />Recent</span>
          {history.slice(0, 5).map((h) => (
            <button key={h.question} disabled={busy} onClick={() => submit(h.question)} title={h.question}
              className="inline-flex max-w-[260px] cursor-pointer items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[13px] text-faint transition-colors hover:text-text disabled:opacity-40">
              <span className={cx("h-1.5 w-1.5 shrink-0 rounded-full", h.status === "ok" ? "bg-verified" : h.status === "cannot_answer" ? "bg-repaired" : "bg-blocked")} />
              <span className="truncate">{h.question}</span>
            </button>
          ))}
          <button onClick={onClearHistory} className="cursor-pointer text-[13px] text-faint underline-offset-2 hover:underline">Clear</button>
        </div>
      )}
    </div>
  );
}
