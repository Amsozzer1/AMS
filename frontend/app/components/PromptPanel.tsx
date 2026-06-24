"use client";

import { useState } from "react";
import { answerPrompt, listPrompts } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

// The v0 money-shot. A pending prompt must be impossible to miss and answerable
// in one click. Polls GET /api/prompts ~1.5s; a websocket live channel is a
// documented later enhancement (see README).
const POLL_MS = 1500;

export default function PromptPanel() {
  const { data, error, refresh } = usePolling(listPrompts, POLL_MS);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const prompts = data ?? [];
  const active = prompts.length > 0;

  async function onDone(id: string) {
    setBusy(id);
    setActionError(null);
    try {
      await answerPrompt(id, "done");
      refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section>
      <h2>Human swap prompts</h2>
      <div className={`prompt-panel${active ? " active" : ""}`}>
        {prompts.map((p) => (
          <div className="prompt-card" key={p.id}>
            <div>
              <div className="module">{p.module_id}</div>
              <div className="msg">{p.message}</div>
            </div>
            <button
              className="btn btn-done"
              onClick={() => onDone(p.id)}
              disabled={busy === p.id}
            >
              {busy === p.id ? "…" : "Done"}
            </button>
          </div>
        ))}
        {!active && (
          <div className="prompt-empty">
            {error
              ? `Could not reach the Brain: ${error}`
              : "No pending swaps. The dashboard is waiting."}
          </div>
        )}
      </div>
      {actionError && <div className="error">{actionError}</div>}
    </section>
  );
}
