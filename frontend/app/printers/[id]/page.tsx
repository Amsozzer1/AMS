import PrinterDetailView from "@/app/components/PrinterDetailView";

// Drill-in detail route for a single printer. `params` is async in Next 15.
export default async function PrinterDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PrinterDetailView id={decodeURIComponent(id)} />;
}
