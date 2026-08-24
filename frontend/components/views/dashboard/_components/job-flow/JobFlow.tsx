"use client";

// Two-step job flow coordinator. JobUpload arms a printer (?start=false); on a successful arm
// it reports which printer, and FilamentMapping appears for that printer so the operator can
// map colours → modules and Confirm & Start. Holding the armed-printer id here (rather than
// in either child) is what keeps both children thin.

import { useState } from "react";
import JobUpload from "./_components/job-upload";
import FilamentMapping from "./_components/filament-mapping";

export default function JobFlow() {
  const [armedPrinter, setArmedPrinter] = useState<string | null>(null);

  return (
    <>
      <JobUpload onArmed={setArmedPrinter} />
      {armedPrinter && <FilamentMapping key={armedPrinter} printerId={armedPrinter} />}
    </>
  );
}
