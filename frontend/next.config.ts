import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lean: no experimental flags, no custom webpack. The UI is a client-rendered
  // dashboard that polls the local Brain API; nothing here needs SSR data.
};

export default nextConfig;
