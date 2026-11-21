import path from "node:path";
import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

export default function config(phase: string): NextConfig {
  return {
    ...(phase === PHASE_DEVELOPMENT_SERVER
      ? { rewrites: async () => [{ source: "/api/:path*", destination: "http://localhost:8000/api/:path*" }] }
      : { output: "export" as const }),
    // Compression buffers small SSE frames in the development proxy.
    compress: false,
    agentRules: false,
    trailingSlash: true,
    skipTrailingSlashRedirect: true,
    outputFileTracingRoot: path.resolve(process.cwd()),
  };
}
