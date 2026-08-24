"use client";

import { API } from "@/api";
import { POLL_MS } from "@/constants";
import { usePolling } from "@/hooks";

/** Brain liveness + mode. A dashboard component, not a `global/` one: it calls `API.health`,
 *  so it is domain-coupled by definition (docs/frontend/00-architecture.md). */
export default function HealthPill() {
  const { data, error } = usePolling((signal) => API.health({ signal }), POLL_MS.HEALTH);
  const ok = !!data?.ok && !error;

  let label = "connecting…";
  if (error) label = "offline";
  else if (data) {
    const mode = data.simulate ? "simulate" : "live";
    label = `${mode} · ${data.printers.length} printer(s) · ${data.modules} module(s)`;
  }

  return (
    <span className={`health-pill${ok ? " ok" : ""}`}>
      <span className="dot" />
      {label}
    </span>
  );
}
