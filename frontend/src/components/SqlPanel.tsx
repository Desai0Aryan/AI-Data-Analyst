import { FlaskConical } from "lucide-react";
import { useState } from "react";
import type { Attempt } from "../lib/types";
import { SqlCode, CopyButton } from "./SqlBlock";
import { Badge, Button, Tabs } from "./ui";

const hasComment = (s: string) => /--|\/\*/.test(s);

export function SqlPanel({ executed, written, tables, limitApplied, limit, onOpenInLab }: {
  executed: string; written: string | null; tables: string[]; limitApplied: boolean; limit: number | null; onOpenInLab: (sql: string) => void;
}) {
  const [which, setWhich] = useState<"executed" | "written">("executed");
  const changes: string[] = [];
  if (written && hasComment(written)) changes.push("Removed comments");
  if (limitApplied && limit) changes.push(`Added LIMIT ${limit.toLocaleString("en-US")}`);
  changes.push("Rebuilt from the parsed query, so the model's raw text is never what runs");

  const shown = which === "written" && written ? written : executed;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <Tabs label="Which SQL" value={which} onChange={setWhich} items={[{ id: "executed", label: "Executed" }, { id: "written", label: "As the model wrote it" }]} />
        <div className="flex gap-2">
          <CopyButton text={shown} />
          <Button onClick={() => onOpenInLab(executed)}><FlaskConical size={15} />Edit in SQL lab</Button>
        </div>
      </div>
      <SqlCode sql={shown} />
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-1.5 text-sm font-semibold">What the guard changed</p>
          <ul className="space-y-1 text-sm text-muted">{changes.map((c) => <li key={c} className="flex gap-2"><span className="text-verified">+</span>{c}</li>)}</ul>
        </div>
        <div>
          <p className="mb-1.5 text-sm font-semibold">Tables read</p>
          <div className="flex flex-wrap gap-1.5">{tables.map((t) => <Badge key={t} tone="signal" className="font-mono">{t}</Badge>)}</div>
        </div>
      </div>
    </div>
  );
}

export const lastWritten = (attempts: Attempt[]) => [...attempts].reverse().find((a) => a.outcome === "ok")?.raw_sql ?? null;
