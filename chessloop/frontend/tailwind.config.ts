import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: {
          900: "rgb(var(--color-ink-900))",
          800: "rgb(var(--color-ink-800))",
          700: "rgb(var(--color-ink-700))",
          600: "rgb(var(--color-ink-600))",
          500: "rgb(var(--color-ink-500))",
          400: "rgb(var(--color-ink-400))",
          300: "rgb(var(--color-ink-300))",
          200: "rgb(var(--color-ink-200))",
          100: "rgb(var(--color-ink-100))",
        },
        gold: {
          900: "rgb(var(--color-gold-900))",
          700: "rgb(var(--color-gold-700))",
          500: "rgb(var(--color-gold-500))",
          400: "rgb(var(--color-gold-400))",
          300: "rgb(var(--color-gold-300))",
          200: "rgb(var(--color-gold-200))",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      boxShadow: {
        glow: "0 0 24px -8px rgba(var(--color-gold-400), 0.6)",
      },
    },
  },
  plugins: [],
} satisfies Config;
