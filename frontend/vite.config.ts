import os from "node:os";
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** Fora de node_modules no CI/Railway evita EBUSY ao rodar `npm ci` com cache de build em camadas. */
const cacheDir =
  process.env.CI === "true" || process.env.RAILWAY_ENVIRONMENT
    ? path.join(os.tmpdir(), "vite-cache-sgp")
    : undefined;

export default defineConfig({
  ...(cacheDir ? { cacheDir } : {}),
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: true,
    port: Number(process.env.PORT) || 3000,
  },
  preview: {
    host: true,
    port: Number(process.env.PORT) || 3000,
    allowedHosts: true,
  },
});
