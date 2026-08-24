import Link from "next/link";

export default function DetailHeader({ id }: { id: string }) {
  return (
    <header className="app-header">
      <div>
        <Link href="/" className="back-link">
          ← Dashboard
        </Link>
        <h1 className="detail-title">
          Printer · <span className="mono">{id}</span>
        </h1>
      </div>
    </header>
  );
}
