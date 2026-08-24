import type { JsonValue } from "@/types";

/** Health / error codes. Rendered first when present — an operator needs to see a fault
 *  before anything else on the page. */
export default function HmsPanel({ messages }: { messages: JsonValue[] }) {
  if (messages.length === 0) return null;
  return (
    <section>
      <h2>Health messages (hms)</h2>
      <div className="hms-list">
        {messages.map((h, i) => (
          <div key={i} className="hms-item">
            <code>{JSON.stringify(h)}</code>
          </div>
        ))}
      </div>
    </section>
  );
}
