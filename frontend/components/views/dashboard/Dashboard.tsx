// The "/" screen — the operator's control surface. This view's only job is composition and
// the order things appear in; every panel owns its own data.

import HealthPill from "./_components/health-pill";
import PromptPanel from "./_components/prompt-panel";
import SwapStrip from "./_components/swap-strip";
import PrinterCards from "./_components/printer-cards";
import JobFlow from "./_components/job-flow";
import SpoolInventory from "./_components/spool-inventory";
import LoadoutPanel from "./_components/loadout-panel";

export default function Dashboard() {
  return (
    <main className="container">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark">AX</span>
          <div>
            <h1>AMS-X Operator</h1>
            <span className="tag">filament swap control surface</span>
          </div>
        </div>
        <HealthPill />
      </header>

      {/* The hero. A pending human-swap prompt must dominate the page — keep it first,
          impossible to miss, answerable in one deliberate action. */}
      <PromptPanel />

      {/* Live swap-loop status for each armed printer. */}
      <SwapStrip />

      <PrinterCards />

      {/* Two-step job flow: pick a file → Upload & Arm → map colours → Confirm & Start. */}
      <JobFlow />

      {/* Secondary: read-the-shop inventory + per-printer module loadout. */}
      <section>
        <div className="section-head">
          <h2>Inventory &amp; loadout</h2>
        </div>
        <div className="inv-grid">
          <SpoolInventory />
          <LoadoutPanel />
        </div>
      </section>
    </main>
  );
}
