"use client";

import { useCallback, useRef, useState } from "react";
import { API, type Prompt } from "@/api";
import { HOLD_MS, parseMessage } from "../../_helpers";

interface PromptCardProps {
  prompt: Prompt;
  onAnswered: () => void;
  onError: (msg: string) => void;
}

/** One pending action. Confirming is a deliberate press-and-hold so it can never happen by
 *  accident — this resumes a real print. Keyboard users get Enter/Space instead. */
export default function PromptCard({ prompt, onAnswered, onError }: PromptCardProps) {
  const { moduleId, instruction } = parseMessage(prompt);
  const [holding, setHolding] = useState(false);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearHold = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    setHolding(false);
  }, []);

  const commit = useCallback(async () => {
    setBusy(true);
    setDone(true);
    try {
      await API.prompts.answer(prompt.id, "done");
      onAnswered();
    } catch (err) {
      setDone(false);
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      setHolding(false);
    }
  }, [prompt.id, onAnswered, onError]);

  const startHold = useCallback(() => {
    if (busy || done) return;
    setHolding(true);
    timer.current = setTimeout(commit, HOLD_MS);
  }, [busy, done, commit]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if ((e.key === "Enter" || e.key === " ") && !busy && !done) {
        e.preventDefault();
        commit();
      }
    },
    [busy, done, commit],
  );

  return (
    <div className="prompt-row">
      <div className="module-callout">
        <span className="label">Module</span>
        <span className="id">{moduleId}</span>
      </div>

      <div className="prompt-body">
        <p className="instruction">{instruction}</p>
        <span className="sub">prompt {prompt.id}</span>
      </div>

      <div>
        <button
          className={`confirm-btn${holding ? " holding" : ""}${done ? " done" : ""}`}
          onPointerDown={startHold}
          onPointerUp={clearHold}
          onPointerLeave={clearHold}
          onKeyDown={onKeyDown}
          disabled={busy || done}
          aria-label={`Mark module ${moduleId} done`}
        >
          <span className="confirm-fill" />
          <span className="confirm-label">{done ? "Resuming print…" : "Hold to mark done"}</span>
        </button>
        {!done && <div className="confirm-hint">press &amp; hold · or Enter</div>}
      </div>
    </div>
  );
}
