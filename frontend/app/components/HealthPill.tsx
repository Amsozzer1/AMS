"use client";

import { getHealth } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

export default function HealthPill() {
  const { data, error } = usePolling(getHealth, 5000);
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
