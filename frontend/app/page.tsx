import HealthPill from "./components/HealthPill";
import JobUpload from "./components/JobUpload";
import PrinterCards from "./components/PrinterCards";
import PromptPanel from "./components/PromptPanel";
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
      <JobUpload />
    </main>
  );
}
