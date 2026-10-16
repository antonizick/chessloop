import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Extra hostnames the dev server accepts (comma-separated), e.g. a Tailscale name:
//   VITE_ALLOWED_HOSTS=localhost,127.0.0.1,myhost.example.ts.net npm run dev
const allowedHosts = (process.env.VITE_ALLOWED_HOSTS ?? "localhost,127.0.0.1")
  .split(",")
  .map((h) => h.trim())
  .filter(Boolean);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 8090,
    strictPort: true,
    host: "0.0.0.0",
    allowedHosts,
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
