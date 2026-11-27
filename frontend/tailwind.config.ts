import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        financial: {
          credit: "#059669",
          creditBg: "#ecfdf5",
          creditBorder: "#a7f3d0",
          debit: "#e11d48",
          debitBg: "#fff1f2",
          debitBorder: "#fecdd3",
          neutral: "#475569",
        },
        engine: {
          brand: "#4f46e5",
          brandHover: "#4338ca",
          locked: "#d97706",
          lockedBg: "#fffbeb",
          driftZero: "#059669",
        },
      },
    },
  },
  plugins: [],
};

export default config;
