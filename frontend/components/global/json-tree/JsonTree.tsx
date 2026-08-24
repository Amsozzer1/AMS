"use client";

// Generic recursive key/value renderer for arbitrary JSON. Surfaces the COMPLETE `raw`
// printer report so nothing the Brain knows is hidden, even for fields the curated sections
// do not model. Objects and non-empty arrays are collapsible; scalars render inline.
//
// Lives in `global/` because it has ZERO domain coupling — it renders any JSON and knows
// nothing about printers (docs/frontend/00-architecture.md).

import type { JsonValue } from "@/types";
import Node from "./_components/node";

/** Render every key of an object as a top-level collapsible tree. */
export default function JsonTree({ data }: { data: { [key: string]: JsonValue } }) {
  const entries = Object.entries(data);
  if (entries.length === 0) {
    return <div className="prompt-empty">No raw data reported yet.</div>;
  }
  return (
    <div className="jt-root">
      {entries.map(([k, v]) => (
        <Node key={k} label={k} value={v} depth={0} />
      ))}
    </div>
  );
}
