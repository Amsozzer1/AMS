import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AMS-X Operator",
  description: "Live printer dashboard, 3MF upload, and the human-swap prompt loop.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
