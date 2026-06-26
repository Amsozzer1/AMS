import HealthPill from "./components/HealthPill";
import JobFlow from "./components/JobFlow";
import LoadoutPanel from "./components/LoadoutPanel";
import PrinterCards from "./components/PrinterCards";
import PromptPanel from "./components/PromptPanel";
import SpoolInventory from "./components/SpoolInventory";
import SwapStrip from "./components/SwapStrip";

export default function Page() {
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

      {/* The hero. A pending human-swap prompt must dominate the page — keep it
          first, impossible to miss, answerable in one deliberate action. */}
      <PromptPanel />

      {/* Live swap-loop status for each armed printer. */}
      <SwapStrip />

      <PrinterCards />

      {/* Two-step job flow: pick a file → Upload & Arm → map colours → Confirm
          & Start. The mapping panel appears once a printer is armed. */}
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
