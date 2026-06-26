"use client";

import { listSpools, type Spool } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

// =============================================================================
// Spool inventory — a compact, read-only list of every spool the Brain knows
// about (Spoolman or the fake store). One line per spool: a real colour swatch,
// name + material, remaining grams, and which module it's loaded in (if any).
//
// Soft by design: Spoolman may be down or unconfigured, so an error or an empty
// list shows a calm empty state — the rest of the dashboard keeps working.
// =============================================================================

const POLL_MS = 5000;

function swatchColor(hex: string | null): string {
  if (hex && /^[0-9a-fA-F]{6}$/.test(hex)) return `#${hex}`;
  return "#9b948333";
}

function grams(g: number | null): string {
  if (typeof g !== "number") return "—";
  return `${Math.round(g)} g`;
}

function SpoolItem({ s }: { s: Spool }) {
  const title = s.name || s.material || s.filament_id || s.id;
  return (
    <div className="spool-item">
      <span
        className="swatch-lg swatch"
        style={{ background: swatchColor(s.color_hex), marginRight: 0 }}
        aria-hidden
      />
      <span className="meta">
        <span className="name">{title}</span>
        <span className="sub">
          {s.material || "—"}
          {s.name && s.material ? "" : ""}
        </span>
      </span>
      <span className="grams">{grams(s.remaining_g)}</span>
      <span className={`mod-chip${s.module ? "" : " empty"}`}>
        {s.module || "unloaded"}
      </span>
    </div>
  );
}

export default function SpoolInventory() {
  const { data, error, loading } = usePolling(listSpools, POLL_MS);
  const spools = (data ?? []).filter((s) => !s.archived);

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Spool inventory</h3>
        {spools.length > 0 && <span className="count">{spools.length}</span>}
      </div>

      {loading && spools.length === 0 && !error ? (
        <p className="mapping-sub">Loading inventory…</p>
      ) : error ? (
        <div className="empty">
          Inventory unavailable — Spoolman may be down or unconfigured.
        </div>
      ) : spools.length === 0 ? (
        <div className="empty">No spools in inventory.</div>
      ) : (
        <div className="spool-list">
          {spools.map((s) => (
            <SpoolItem key={s.id} s={s} />
          ))}
        </div>
      )}
    </div>
  );
}
