import type { Metadata } from "next";
import { Bricolage_Grotesque, Archivo, Space_Mono } from "next/font/google";
// Style order is load-bearing (CLAUDE.md RULE 1 does not suspend the cascade):
//   1. globals  — design tokens, resets, layout shell, shared primitives
//   2. views    — one file per view, colocated with it
//   3. responsive — LAST, so its media queries win at equal specificity
import "./globals.css";

import "@/components/views/dashboard/_helpers/dashboard.styles.css";
import "@/components/views/dashboard/_components/health-pill/_helpers/health-pill.styles.css";
import "@/components/views/dashboard/_components/prompt-panel/_helpers/prompt-panel.styles.css";
import "@/components/views/dashboard/_components/printer-cards/_helpers/printer-cards.styles.css";
import "@/components/views/dashboard/_components/swap-strip/_helpers/swap-strip.styles.css";
import "@/components/views/dashboard/_components/job-flow/_components/job-upload/_helpers/job-upload.styles.css";
import "@/components/views/dashboard/_components/job-flow/_components/filament-mapping/_helpers/filament-mapping.styles.css";
import "@/components/views/dashboard/_components/spool-inventory/_helpers/spool-inventory.styles.css";
import "@/components/views/printer-detail/_helpers/printer-detail.styles.css";

import "./responsive.css";

// Display — a characterful grotesque for the masthead, section heads, and the big
// module callout on the work-order placard. Designed, not default.
const display = Bricolage_Grotesque({
  subsets: ["latin"],
  weight: ["400", "600", "700", "800"],
  variable: "--font-display",
  display: "swap",
});

// UI / body — a clean technical grotesque for labels and prose.
const body = Archivo({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body",
  display: "swap",
});

// Data — a typewriter-grade mono for telemetry, codes, and eyebrows (engineering-doc feel).
const mono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AMS-X Operator",
  description:
    "Live printer telemetry, 3MF job intake, and the human-swap work order.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${mono.variable} ${body.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
