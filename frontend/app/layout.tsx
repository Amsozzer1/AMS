import type { Metadata } from "next";
import { Bricolage_Grotesque, Archivo, Space_Mono } from "next/font/google";
import "./globals.css";

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
