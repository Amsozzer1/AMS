"use client";

import { useCallback, useRef, useState } from "react";
import { answerPrompt, listPrompts, type Prompt } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

// =============================================================================
// THE HERO — the v0 money-shot.
//
// When GET /api/prompts is non-empty a human action is pending: the server has
// paused a real print and is waiting for the operator to feed a module. This
// panel turns into a full amber "Action Console" — a beacon, the physical module
// address, the instruction, and ONE deliberate hold-to-confirm button that POSTs
// the answer and resumes the print. Completing it should feel intentional and
// satisfying, never accidental.
// =============================================================================

const POLL_MS = 1000;
const HOLD_MS = 600; // press-and-hold duration; must match the CSS fill transition

// The server message is free text like "[module m2] START FEEDING…" or
// "Module m2 — START FEEDING filament 3". The module is already shown as a big
// callout, so strip the leading "[module X]" / "Module X —" prefix and keep only
// the instruction. Falls back gracefully if the format differs.
function parseMessage(p: Prompt): { moduleId: string; instruction: string } {
  const moduleId = p.module_id || "—";
  let instruction = p.message?.trim() || "Feed the requested module, then confirm.";
  const stripped = instruction
    .replace(/^\[?\s*module\s+[^\]\s]+\s*\]?\s*[—\-:]?\s*/i, "")
    .trim();
  if (stripped) instruction = stripped;
  return { moduleId, instruction };
}

function PromptCard({
  prompt,
  onAnswered,
  onError,
}: {
  prompt: Prompt;
  onAnswered: () => void;
  onError: (msg: string) => void;
}) {
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
      await answerPrompt(prompt.id, "done");
      // Brief confirmed state, then let the poll drop this prompt from the list.
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

  // Keyboard: Enter/Space confirms immediately (hold gesture is pointer-only).
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
          <span className="confirm-label">
            {done ? "Resuming print…" : "Hold to mark done"}
          </span>
        </button>
        {!done && <div className="confirm-hint">press &amp; hold · or Enter</div>}
      </div>
    </div>
  );
}

export default function PromptPanel() {
  const { data, error, refresh } = usePolling(listPrompts, POLL_MS);
  const [actionError, setActionError] = useState<string | null>(null);
  const prompts = data ?? [];
  const active = prompts.length > 0;

  return (
    <section aria-live="assertive" aria-label="Pending human-swap actions">
      <div className="section-head">
        <h2>Action console</h2>
        {active && <span className="count">{prompts.length} pending</span>}
      </div>

      {active ? (
        <div className="action-console console-active">
          <div className="beacon" aria-hidden />
          <div className="console-banner">
            <span className="pulse-dot" aria-hidden />
            Action required — print is paused
          </div>
          <div className="prompt-stack">
            {prompts.map((p) => (
              <PromptCard
                key={p.id}
                prompt={p}
                onAnswered={() => {
                  setActionError(null);
                  refresh();
                }}
                onError={setActionError}
              />
            ))}
          </div>
          {actionError && <div className="console-error">{actionError}</div>}
        </div>
      ) : (
        <div className="console-idle">
          <span className="standby-dot" aria-hidden />
          {error ? (
            <span className="err">Brain unreachable — {error}</span>
          ) : (
            <span>Standing by. No swap action pending.</span>
          )}
        </div>
      )}
    </section>
  );
}
