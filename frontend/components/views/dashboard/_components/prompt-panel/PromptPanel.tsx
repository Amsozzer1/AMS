"use client";

// THE HERO — the v0 money-shot. When GET /api/prompts is non-empty a human action is
// pending: the server has paused a real print and is waiting for the operator to feed a
// module. The panel becomes a full amber "Action Console" — beacon, module address,
// instruction, and one deliberate hold-to-confirm that resumes the print.

import { useState } from "react";
import { API } from "@/api";
import { POLL_MS } from "@/constants";
import { usePolling } from "@/hooks";
import PromptCard from "./_components/prompt-card";

export default function PromptPanel() {
  const { data, error, refresh } = usePolling(
    (signal) => API.prompts.list({ signal }),
    POLL_MS.PROMPTS,
  );
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
