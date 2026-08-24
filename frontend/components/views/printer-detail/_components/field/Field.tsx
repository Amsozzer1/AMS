/** One label/value row in a detail grid.
 *
 *  A leaf primitive shared by this view's section components. It stays at the view's
 *  `_components` root (rather than `global/`) because its styling is specific to the
 *  detail grid — siblings import it as `../field`. */
export default function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="detail-field">
      <span className="detail-field-k">{label}</span>
      <span className="detail-field-v">{children}</span>
    </div>
  );
}
