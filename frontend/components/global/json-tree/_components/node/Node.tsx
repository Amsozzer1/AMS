"use client";

import { useState } from "react";
import type { JsonValue } from "@/types";
import { isContainer, summarize } from "../../_helpers";
import ScalarValue from "../scalar-value";

interface NodeProps {
  label: string;
  value: JsonValue;
  depth: number;
  defaultOpen?: boolean;
}

/** One row: a key plus either an inline scalar or a collapsible nested node.
 *  Recurses into itself for containers; only depth 0 may start open. */
export default function Node({ label, value, depth, defaultOpen }: NodeProps) {
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
