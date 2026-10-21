import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// В dev-режиме API проксируется на локальный uvicorn — фронт и бэкенд на одном origin, как за nginx.
const backend = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": backend,
      "/health": backend,
      "/companies": backend,
    },
  },
});
