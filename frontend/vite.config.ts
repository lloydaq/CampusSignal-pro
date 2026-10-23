/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Development and tests only: the SPA calls the API with relative URLs (same origin, as behind
// Caddy in deployments, architecture.md §3), and the dev and preview servers forward them to
// uvicorn. The full-stack E2E run (playwright.fullstack.config.ts) uses the preview proxy.
const DEV_API_TARGET = "http://127.0.0.1:8000";
const API_PROXY = {
  "/api": DEV_API_TARGET,
  "/healthz": DEV_API_TARGET,
  "/readyz": DEV_API_TARGET,
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: API_PROXY,
  },
  preview: {
    proxy: API_PROXY,
  },
  test: {
    environment: "jsdom",
    // Unit and component tests only; browser tests in e2e/ run under Playwright.
    include: ["src/**/*.test.{ts,tsx}"],
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
    restoreMocks: true,
  },
});
