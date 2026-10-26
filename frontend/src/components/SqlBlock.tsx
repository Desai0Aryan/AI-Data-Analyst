import { Check, Copy } from "lucide-react";
import { Fragment, useState } from "react";
import { tokenizeSql } from "../lib/sqlHighlight";
import { Button, cx } from "./ui";

export function SqlCode({ sql, className }: { sql: string; className?: string }) {
  const lines = sql.split("\n");
  return (
    <pre className={cx("scroll-thin overflow-auto rounded-xl bg-sunken p-4 font-mono text-[13px] leading-[1.7]", className)}>
      <code>
        {lines.map((line, i) => (
          <div key={i} className="flex">
            <span className="mr-4 w-6 shrink-0 select-none text-right text-faint tnum" aria-hidden>{i + 1}</span>
            <span className="whitespace-pre">
              {tokenizeSql(line).map((t, k) => <Fragment key={k}>{t.kind === "ws" || t.kind === "id" ? t.text : <span className={`sql-${t.kind}`}>{t.text}</span>}</Fragment>)}
            </span>
          </div>
        ))}
      </code>
    </pre>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button onClick={async () => { try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1400); } catch { /* ignore */ } }}>
      {done ? <Check size={15} /> : <Copy size={15} />}{done ? "Copied" : label}
    </Button>
  );
}
