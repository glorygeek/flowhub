import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#f3f7f6",
        card: "#ffffff",
        ink: "#0f172a",
        accent: "#0f766e",
        muted: "#64748b"
      }
    }
  },
  plugins: []
};

export default config;
