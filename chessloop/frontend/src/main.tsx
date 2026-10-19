import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { useAuthStore } from "@/stores/auth";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
  },
});

// Forget every cached answer when someone signs out or a different person signs in.
// Without this, the next person on the same browser tab briefly sees the previous
// person's libraries and stats (cached for 30 s) until the page is reloaded.
useAuthStore.subscribe((state, prev) => {
  if ((prev.accessToken && !state.accessToken) || (prev.user && state.user && prev.user.id !== state.user.id)) {
    queryClient.clear();
  }
});

function sendClientLog(level: string, message: string, stack?: string) {
  fetch("/api/logs/client", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ level, message, stack, url: window.location.href }),
  }).catch(() => {});
}

window.addEventListener("error", (e) => {
  sendClientLog("error", e.message, e.error?.stack);
});

window.addEventListener("unhandledrejection", (e) => {
  const msg = e.reason instanceof Error ? e.reason.message : String(e.reason);
  const stack = e.reason instanceof Error ? e.reason.stack : undefined;
  sendClientLog("error", `Unhandled rejection: ${msg}`, stack);
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
