"use client";

// Live swap-loop status, one strip per printer. Before a job is armed the endpoint returns
// `{ armed: false }` and the strip renders nothing. Thin client: pure render of server state.

import { API } from "@/api";
import { POLL_MS } from "@/constants";
import { usePolling } from "@/hooks";
import OrchStrip from "./_components/orch-strip";

export default function SwapStrip() {
  const { data } = usePolling(
    (signal) => API.printers.list({ signal }),
    POLL_MS.SWAP_STRIP_PRINTERS,
  );
  const printers = data ?? [];
  if (printers.length === 0) return null;

  return (
    <div style={{ marginBottom: "var(--s-6)" }}>
      {printers.map((p) => (
        <OrchStrip key={p.id} printerId={p.id} />
      ))}
    </div>
  );
}
