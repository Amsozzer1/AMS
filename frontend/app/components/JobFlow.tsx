"use client";

import { useState } from "react";
import FilamentMapping from "./FilamentMapping";
import JobUpload from "./JobUpload";

// Two-step job flow coordinator. JobUpload arms a printer (?start=false); on a
// successful arm it reports which printer, and we reveal FilamentMapping for that
// printer so the operator can map colours → modules and Confirm & Start. Keeping
// the armed-printer id here (rather than in either child) keeps each child thin.
export default function JobFlow() {
  const [armedPrinter, setArmedPrinter] = useState<string | null>(null);

  return (
    <>
      <JobUpload onArmed={setArmedPrinter} />
      {armedPrinter && (
        <FilamentMapping key={armedPrinter} printerId={armedPrinter} />
      )}
    </>
  );
}
