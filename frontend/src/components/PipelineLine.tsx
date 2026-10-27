import { motion, useReducedMotion } from "framer-motion";
import { BadgeCheck, Braces, Check, Database, MessageSquareText, RotateCcw, ShieldCheck, X } from "lucide-react";
import type { ReactNode } from "react";
import { STATION_ORDER, type Loop, type PipelineState, type StationId, type StationStatus } from "../lib/pipelineState";
import { cx } from "./ui";

const META: Record<StationId, { label: string; icon: ReactNode }> = {
  ask: { label: "Ask", icon: <MessageSquareText size={20} /> },
  write: { label: "Write SQL", icon: <Braces size={20} /> },
  guard: { label: "Guard", icon: <ShieldCheck size={20} /> },
  run: { label: "Run", icon: <Database size={20} /> },
  verify: { label: "Verify", icon: <BadgeCheck size={20} /> },
};

// Station centers as a percentage of the track width.
const PAD = 8;
export const stationX = (i: number) => PAD + (i * (100 - 2 * PAD)) / (STATION_ORDER.length - 1);

const RING: Record<StationStatus, string> = {
  idle: "border-line text-faint bg-surface",
  active: "border-signal text-signal bg-signal/10 packet-pulse",
  done: "border-verified/70 text-verified bg-verified/10",
  blocked: "border-blocked text-blocked bg-blocked/10",
  repaired: "border-repaired text-repaired bg-repaired/10",
};

function Badge({ status }: { status: StationStatus }) {
  const common = "absolute -right-1 -top-1 grid h-5 w-5 place-items-center rounded-full border-2 border-page";
  if (status === "done") return <span className={cx(common, "bg-verified text-page")}><Check size={11} strokeWidth={3.4} /></span>;
  if (status === "blocked") return <span className={cx(common, "bg-blocked text-page")}><X size={11} strokeWidth={3.4} /></span>;
  if (status === "repaired") return <span className={cx(common, "bg-repaired text-page")}><RotateCcw size={10} strokeWidth={3.2} /></span>;
  return null;
}

/** An arc from the station that rejected the query back to "Write SQL": the repair loop, drawn literally. */
function LoopArc({ loop, index }: { loop: Loop; index: number }) {
  const from = STATION_ORDER.indexOf(loop.from);
  const to = STATION_ORDER.indexOf("write");
  const x1 = stationX(from) * 10, x2 = stationX(to) * 10;
  const lift = 36 + (index % 3) * 10;
  const color = loop.from === "verify" ? "var(--color-repaired)" : "var(--color-blocked)";
  return (
    <motion.path
      d={`M ${x1} 62 C ${x1} ${62 - lift * 2}, ${x2} ${62 - lift * 2}, ${x2} 62`}
      fill="none" stroke={color} strokeWidth={2} strokeDasharray="5 6" vectorEffect="non-scaling-stroke"
      initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: 0.9 }} transition={{ duration: 0.7, ease: "easeOut" }}
    />
  );
}

export function PipelineLine({ state }: { state: PipelineState }) {
  const reduce = useReducedMotion();
  const packetIndex = STATION_ORDER.indexOf(state.packetAt);
  const running = state.phase === "running";
  const progress = state.phase === "idle" ? 0 : stationX(packetIndex);
  const label = state.draftSql ? state.draftSql.replace(/\s+/g, " ").slice(0, 26) : state.phase === "idle" ? "" : "…";

  return (
    <div className="relative select-none" role="group" aria-label="Pipeline progress" aria-live="polite">
      <div className="relative h-[176px] sm:h-[132px]">
        {/* repair loops */}
        <svg className="pointer-events-none absolute inset-x-0 top-0 h-[132px] w-full overflow-visible" viewBox="0 0 1000 132" preserveAspectRatio="none" aria-hidden>
          {state.loops.map((l, i) => <LoopArc key={`${l.attempt}-${l.from}-${i}`} loop={l} index={i} />)}
        </svg>

        {/* track */}
        <div className="absolute top-[62px] h-[3px] -translate-y-1/2 rounded-full bg-line/70" style={{ left: `${stationX(0)}%`, right: `${stationX(0)}%` }} />
        <motion.div
          className="absolute top-[62px] h-[3px] -translate-y-1/2 rounded-full bg-signal"
          style={{ left: `${stationX(0)}%` }}
          animate={{ width: `${Math.max(0, progress - stationX(0))}%` }}
          transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 90, damping: 18 }}
        />

        {/* the query, travelling */}
        {(state.phase === "running" || (state.phase !== "idle" && state.draftSql)) && (
          <motion.div
            className="absolute top-[62px] z-10"
            style={{ transform: `translate(-${(packetIndex / (STATION_ORDER.length - 1)) * 100}%, -52px)` }}   // anchored so it never leaves the panel
            animate={{ left: `${stationX(packetIndex)}%` }}
            transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 110, damping: 17 }}
          >
            <div className={cx("max-w-[150px] truncate rounded-md border px-2 sm:max-w-[190px] py-0.5 font-mono text-[11px]",
              running ? "border-signal/60 bg-page text-signal" : state.phase === "error" ? "border-blocked/60 bg-page text-blocked" : "border-line bg-page text-muted")}>
              {label}
            </div>
          </motion.div>
        )}

        {/* stations */}
        {STATION_ORDER.map((id, i) => {
          const st = state.stations[id];
          return (
            <div key={id} className="absolute top-[62px] w-[17%] -translate-x-1/2 -translate-y-[26px] text-center" style={{ left: `${stationX(i)}%` }} data-station={id} data-status={st.status}>
              <div
                key={st.status === "blocked" ? `b${state.loops.length}` : st.status}
                className={cx("relative mx-auto grid h-[52px] w-[52px] place-items-center rounded-full border-2 transition-colors duration-300", RING[st.status], st.status === "blocked" && "shake")}
              >
                {META[id].icon}
                <Badge status={st.status} />
              </div>
              <p className={cx("mt-2 text-[15px] font-semibold", st.status === "idle" ? "text-muted" : "text-text")}>{META[id].label}</p>
              <p className={cx("mx-auto mt-0.5 min-h-[34px] max-w-[190px] text-[12.5px] leading-[1.35]",
                st.status === "blocked" ? "text-blocked" : st.status === "repaired" ? "text-repaired" : st.status === "done" ? "text-verified" : "text-faint")}>
                {st.caption}
              </p>
            </div>
          );
        })}
      </div>

      {state.attempt > 1 && state.phase === "running" && (
        <p className="mt-1 text-center text-[13px] text-repaired">Retrying with the error as feedback: attempt {state.attempt} of {state.maxAttempts}</p>
      )}
    </div>
  );
}
