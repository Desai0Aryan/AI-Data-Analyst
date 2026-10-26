import type { ButtonHTMLAttributes, ReactNode } from "react";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

export function Panel({ className, children, ...rest }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLElement>) {
  return <section className={cx("rounded-[14px] border border-line/70 bg-surface", className)} {...rest}>{children}</section>;
}

type Tone = "signal" | "verified" | "blocked" | "repaired" | "muted";
const TONES: Record<Tone, string> = {
  signal: "bg-signal/15 text-signal border-signal/30",
  verified: "bg-verified/12 text-verified border-verified/30",
  blocked: "bg-blocked/12 text-blocked border-blocked/30",
  repaired: "bg-repaired/12 text-repaired border-repaired/30",
  muted: "bg-raised text-muted border-line/60",
};
export function Badge({ tone = "muted", children, className, title }: { tone?: Tone; children: ReactNode; className?: string; title?: string }) {
  return <span title={title} className={cx("inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[12.5px] font-medium leading-5", TONES[tone], className)}>{children}</span>;
}

export function Button({ variant = "ghost", className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  const base = "inline-flex items-center justify-center gap-2 rounded-[10px] px-3.5 py-2 text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer";
  const styles = {
    primary: "bg-signal text-page hover:bg-[#a6b4ff]",
    ghost: "border border-line/80 text-text hover:bg-raised",
    danger: "border border-blocked/50 text-blocked hover:bg-blocked/10",
  }[variant];
  return <button className={cx(base, styles, className)} {...rest} />;
}

export function Tabs<T extends string>({ value, onChange, items, label }: { value: T; onChange: (v: T) => void; items: { id: T; label: string; icon?: ReactNode }[]; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex rounded-[10px] bg-sunken p-1">
      {items.map((t) => (
        <button
          key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={cx("inline-flex cursor-pointer items-center gap-1.5 rounded-[8px] px-3 py-1.5 text-sm font-medium transition-colors",
            value === t.id ? "bg-raised text-text" : "text-muted hover:text-text")}
        >{t.icon}{t.label}</button>
      ))}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded-md border border-line/80 bg-sunken px-1.5 py-0.5 font-mono text-[11px] text-muted">{children}</kbd>;
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-14 text-center">
      {icon && <div className="text-faint">{icon}</div>}
      <p className="text-base font-semibold">{title}</p>
      {children && <div className="max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}
