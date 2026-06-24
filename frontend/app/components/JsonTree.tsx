"use client";

// Generic recursive key/value renderer for arbitrary JSON. Used to surface the
// COMPLETE `raw` printer report so nothing the Brain knows is hidden, even for
// fields the curated section does not model. Objects and non-empty arrays are
// collapsible; scalars render inline. Pure presentation — no API knowledge.

import { useState } from "react";
import type { JsonValue } from "@/lib/api";

function isContainer(v: JsonValue): v is JsonValue[] | { [k: string]: JsonValue } {
  return v !== null && typeof v === "object";
}

function summarize(v: JsonValue): string {
  if (Array.isArray(v)) return `[ ${v.length} ]`;
  return `{ ${Object.keys(v as object).length} }`;
}

type Scalar = string | number | boolean | null;

function ScalarValue({ value }: { value: Scalar }) {
  if (value === null) return <span className="jt-null">null</span>;
  if (typeof value === "boolean")
    return <span className="jt-bool">{String(value)}</span>;
  if (typeof value === "number")
    return <span className="jt-num">{value}</span>;
  return <span className="jt-str">{value}</span>;
}

/** One row: a key plus either an inline scalar or a collapsible nested node. */
function Node({
  label,
  value,
  depth,
  defaultOpen,
}: {
  label: string;
  value: JsonValue;
  depth: number;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(depth < 1 && (defaultOpen ?? false));

  if (!isContainer(value)) {
    return (
      <div className="jt-row">
        <span className="jt-key">{label}</span>
        <ScalarValue value={value} />
      </div>
    );
  }

  const entries: [string, JsonValue][] = Array.isArray(value)
    ? value.map((v, i) => [String(i), v])
    : Object.entries(value);
  const empty = entries.length === 0;

  return (
    <div className="jt-node">
      <button
        type="button"
        className="jt-toggle"
        onClick={() => !empty && setOpen((o) => !o)}
        disabled={empty}
        aria-expanded={open}
      >
        <span className="jt-caret">{empty ? "·" : open ? "▾" : "▸"}</span>
        <span className="jt-key">{label}</span>
        <span className="jt-summary">{summarize(value)}</span>
      </button>
      {open && !empty && (
        <div className="jt-children">
          {entries.map(([k, v]) => (
            <Node key={k} label={k} value={v} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Render every key of an object as a top-level collapsible tree. */
export default function JsonTree({
  data,
}: {
  data: { [key: string]: JsonValue };
}) {
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
