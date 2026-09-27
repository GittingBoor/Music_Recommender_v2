import type { Config } from "tailwindcss";

// Colours are CSS variables (RGB channels, see index.css) so opacity
// modifiers like `bg-signal/10` keep working. The default Tailwind palette is
// replaced on purpose: only the tokens below exist.
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      black: "#000",
      white: "#fff",
      ground: token("ground"),
      panel: token("panel"),
      raised: token("raised"),
      line: token("line"),
      "line-strong": token("line-strong"),
      ink: token("ink"),
      "ink-2": token("ink-2"),
      "ink-3": token("ink-3"),
      "ink-4": token("ink-4"),
      signal: token("signal"),
      ok: token("ok"),
      warn: token("warn"),
      bad: token("bad"),
    },
    fontFamily: {
      sans: ["Archivo", "system-ui", "Segoe UI", "sans-serif"],
      mono: ['"IBM Plex Mono"', "ui-monospace", "Consolas", "monospace"],
    },
    fontSize: {
      "2xs": ["11px", "14px"],
      xs: ["12px", "16px"],
      sm: ["13px", "18px"],
      base: ["14px", "20px"],
      md: ["16px", "22px"],
      lg: ["20px", "24px"],
      xl: ["24px", "28px"],
      "2xl": ["32px", "34px"],
      "3xl": ["44px", "44px"],
    },
    borderRadius: {
      none: "0",
      sm: "2px",
      DEFAULT: "2px",
      full: "9999px",
    },
    extend: {},
  },
  plugins: [],
} satisfies Config;
