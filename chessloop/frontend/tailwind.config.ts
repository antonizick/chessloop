import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: {
          900: "#0a0a0b",
          800: "#121215",
          700: "#1a1a1f",
          600: "#262630",
          500: "#3a3a47",
          400: "#5a5a6b",
          300: "#8b8b9c",
          200: "#c4c4d0",
          100: "#e8e8ee",
        },
        gold: {
          900: "#3a2c08",
          700: "#7a5b14",
          500: "#c79a2d",
          400: "#d4af44",
          300: "#e5c466",
          200: "#f0d99a",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      boxShadow: {
        glow: "0 0 24px -8px rgba(212, 175, 68, 0.6)",
      },
    },
  },
  plugins: [],
} satisfies Config;
