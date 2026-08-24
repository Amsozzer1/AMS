/** Resolve a bare 6-hex RRGGBB (no `#`) to a CSS colour.
 *
 *  Falls back to a translucent neutral when the value is missing or malformed, so an unknown
 *  colour reads as "no swatch" rather than rendering black. Was duplicated byte-for-byte in
 *  three components before this file existed. */
export function swatchColor(hex: string | null | undefined): string {
  if (hex && /^[0-9a-fA-F]{6}$/.test(hex)) return `#${hex}`;
  return "#9b948333";
}
