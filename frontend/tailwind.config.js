/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        f1: {
          black: "#000000",
          dark: "#050505",
          surface: "#0a0a0a",
          "surface-light": "#141414",
          border: "#1a1a1a",
          red: "#e10600",
          "red-hover": "#ff1a1a",
          text: "#f0f0f0",
          muted: "#666680",
          sidebar: "#000000",
          "sidebar-hover": "#0a0a0a",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
        display: ["Oswald", "sans-serif"],
      },
      animation: {
        "pulse-dot": "pulse-dot 1.4s infinite ease-in-out both",
        "scroll": "scroll 30s linear infinite",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 80%, 100%": { transform: "scale(0)" },
          "40%": { transform: "scale(1)" },
        },
        "scroll": {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
      },
    },
  },
  plugins: [],
};
