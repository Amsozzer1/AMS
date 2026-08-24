/** A labelled text/number input. Collapses six near-identical field blocks into one. */
export default function TextField({
  id,
  label,
  value,
  onChange,
  disabled,
  type = "text",
  placeholder,
  required,
  min,
  step,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  type?: "text" | "number";
  placeholder?: string;
  required?: boolean;
  min?: number;
  step?: number;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        className="spool-text-input"
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        disabled={disabled}
        min={min}
        step={step}
      />
    </div>
  );
}
