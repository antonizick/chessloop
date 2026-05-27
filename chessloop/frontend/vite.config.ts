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
    host: true,
    allowedHosts: ['.ts.net'],        // Allow Tailscale Funnel access
    hmr: {
      // Allow HMR connections from both localhost and Tailscale
      // Vite auto-detects the host from the browser request
      host: undefined,
      protocol: 'ws',
    },
    proxy: {
      "/api": {
        target: "http://localhost:8100",
        changeOrigin: true,
      },
    },
  },
  preview: { port: 8090 },
});
