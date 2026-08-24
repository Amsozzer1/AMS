import JsonTree from "@/components/global/json-tree";
import type { JsonValue } from "@/types";

/** The printer's COMPLETE own report, rendered generically so nothing the Brain knows is
 *  hidden — including fields the curated sections above do not model. */
export default function RawSection({ raw }: { raw: { [key: string]: unknown } }) {
  return (
    <section>
      <h2>Raw report (everything)</h2>
      <p className="prompt-empty" style={{ marginBottom: 12 }}>
        The printer&apos;s complete own report. Click any object or array to expand.
      </p>
      <div className="raw-tree">
        <JsonTree data={(raw ?? {}) as { [k: string]: JsonValue }} />
      </div>
    </section>
  );
}
