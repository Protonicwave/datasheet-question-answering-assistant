import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the API runs separately (`datasheet-assistant serve`), so
// Vite forwards /api to it. In production the API serves the built page.
const API_ORIGIN = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": API_ORIGIN } },
  test: { environment: "jsdom" },
});
