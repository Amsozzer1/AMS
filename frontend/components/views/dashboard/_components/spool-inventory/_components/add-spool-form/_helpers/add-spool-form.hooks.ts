"use client";

import { useCallback, useEffect, useState } from "react";
import { API, type ModuleInfo } from "@/api";

/** Form state + submit for the add-spool disclosure.
 *
 *  `hasColor` exists because `<input type="color">` has no empty state — without the opt-out
 *  every colourless spool would silently be created white. When it is off, `color_hex` is
 *  omitted entirely rather than sent as a default. */
export function useAddSpoolForm(onSuccess: () => void) {
  const [material, setMaterial] = useState("");
  const [color, setColor] = useState("#ffffff");
  const [hasColor, setHasColor] = useState(true);
  const [name, setName] = useState("");
  const [vendor, setVendor] = useState("");
  const [initialG, setInitialG] = useState("1000");
  const [moduleId, setModuleId] = useState("");
  const [modules, setModules] = useState<ModuleInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    API.modules
      .list({ signal: controller.signal })
      .then(setModules)
      .catch(() => {
        /* non-fatal: the form works without a module selection */
      });
    return () => controller.abort();
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!material.trim()) {
        setError("Material is required.");
        return;
      }
      const grams = parseFloat(initialG);
      if (isNaN(grams) || grams < 0) {
        setError("Initial grams must be a non-negative number.");
        return;
      }
      setBusy(true);
      setError(null);
      try {
        await API.spools.create({
          material: material.trim(),
          // The server wants bare 6-hex, no leading '#'.
          color_hex: hasColor ? color.replace(/^#/, "") : undefined,
          name: name.trim() || undefined,
          vendor: vendor.trim() || undefined,
          initial_g: grams,
          module: moduleId || undefined,
        });
        onSuccess();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [material, color, hasColor, name, vendor, initialG, moduleId, onSuccess],
  );

  return {
    material, setMaterial,
    color, setColor,
    hasColor, setHasColor,
    name, setName,
    vendor, setVendor,
    initialG, setInitialG,
    moduleId, setModuleId,
    modules, busy, error, handleSubmit,
  };
}
