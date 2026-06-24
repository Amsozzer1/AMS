import HealthPill from "./components/HealthPill";
import JobUpload from "./components/JobUpload";
import PrinterCards from "./components/PrinterCards";
import PromptPanel from "./components/PromptPanel";

export default function Page() {
  return (
    <main className="container">
      <header className="app-header">
        <h1>AMS-X Operator</h1>
        <HealthPill />
      </header>

      {/* The prompt loop is the priority — keep it at the top, impossible to miss. */}
      <PromptPanel />
      <PrinterCards />
      <JobUpload />
    </main>
  );
}
