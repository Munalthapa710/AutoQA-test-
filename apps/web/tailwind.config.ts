import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#091018",
        ember: "#ff6f3c",
        mist: "#d9f2ff",
        sand: "#f4ede5",
        slate: "#113046",
      },
      boxShadow: {
        pane: "0 20px 60px rgba(9, 16, 24, 0.14)",
      },
      backgroundImage: {
        grid: "linear-gradient(to right, rgba(17,48,70,0.08) 1px, transparent 1px), linear-gradient(to bottom, rgba(17,48,70,0.08) 1px, transparent 1px)",
      },
      fontFamily: {
        display: ["var(--font-space-grotesk)"],
        mono: ["var(--font-ibm-plex-mono)"],
      },
    },
  },
  plugins: [],
};

export default config;
