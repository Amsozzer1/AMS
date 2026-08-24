import type { Scalar } from "../../_helpers";

/** One JSON leaf, class-tagged by type so the stylesheet can colour it. */
export default function ScalarValue({ value }: { value: Scalar }) {
  if (value === null) return <span className="jt-null">null</span>;
  if (typeof value === "boolean") return <span className="jt-bool">{String(value)}</span>;
  if (typeof value === "number") return <span className="jt-num">{value}</span>;
  return <span className="jt-str">{value}</span>;
}
