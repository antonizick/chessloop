import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 8090,
    strictPort: true,
    host: "0.0.0.0",
    allowedHosts: [
      "localhost",
      "127.0.0.1",
      "bld2.taild1bb43.ts.net",
      ".ts.net",  // Allow all Tailscale addresses
    ],
    hmr: {
      // Auto-detect host and protocol from browser request
      host: undefined,
      protocol: "auto",
      timeout: 10000,
    },
    proxy: {
      "/api": {
        target: "http://localhost:8100",
        changeOrigin: true,
        ws: true,  // Enable WebSocket proxy if needed
      },
    },
  },
  preview: { port: 8090 },
});
