import { useCallback, useEffect, useReducer, useRef } from "react";
import { ApiError, askStream } from "./api";
import { Pacer } from "./pacer";
import { delayFor, initialState, pipelineReducer } from "./pipelineState";
import type { PipelineEvent } from "./types";

/** Streams a question through the pipeline and exposes live state for the pipeline line. */
export function useAsk() {
  const [state, dispatch] = useReducer(pipelineReducer, initialState);
  const abort = useRef<AbortController | null>(null);
  const pacer = useRef<Pacer<PipelineEvent> | null>(null);

  const stop = useCallback(() => {
    abort.current?.abort();
    pacer.current?.clear();
  }, []);

  const run = useCallback(async (question: string) => {
    stop();
    const ctl = new AbortController();
    abort.current = ctl;
    const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    const p = new Pacer<PipelineEvent>((event) => dispatch({ type: "event", event }), (e) => delayFor(e, reduce));
    pacer.current = p;
    dispatch({ type: "begin", question });
    try {
      await askStream(question, (e) => p.push(e), ctl.signal);
      await p.idle();
    } catch (err) {
      p.clear();
      const d = err instanceof ApiError ? err.detail : { stage: "client", code: "unknown", message: "Something went wrong." };
      dispatch({ type: "event", event: { type: "error", ...d } });
    }
  }, [stop]);

  const reset = useCallback(() => { stop(); dispatch({ type: "reset" }); }, [stop]);
  useEffect(() => stop, [stop]);
  return { state, run, reset };
}
