/** The Brain only parses a sliced `.gcode.3mf`.
 *
 *  Browsers key `accept` off a single trailing extension and ignore the double
 *  `.gcode.3mf` (they show all `.3mf` files), so the browse dialog filters on `.3mf` and this
 *  enforces the full suffix — which also covers drag-and-drop, where `accept` does nothing. */
export function isSliced3mf(f: File): boolean {
  return f.name.toLowerCase().endsWith(".gcode.3mf");
}

/** The `accept` attribute for the browse dialog. Deliberately looser than `isSliced3mf`. */
export const FILE_ACCEPT =
  ".gcode.3mf,.3mf,model/3mf,application/vnd.ms-package.3dmanufacturing-3dmodelplus+xml";
