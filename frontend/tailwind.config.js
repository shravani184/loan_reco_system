/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm, approachable accent — a soft terracotta/rust rather than corporate blue.
        brand: {
          DEFAULT: "#b3562b",
          dark: "#8f4322",
          light: "#d1794b",
          tint: "#f7ece5",
        },
        // Muted warm neutrals used across the UI.
        ink: {
          DEFAULT: "#3d342d",
          soft: "#6b5f55",
          faint: "#9a8d83",
        },
        paper: {
          DEFAULT: "#faf7f3",
          line: "#e9e2da",
        },
      },
      boxShadow: {
        soft: "0 1px 2px rgba(80,60,40,0.06), 0 4px 16px rgba(80,60,40,0.05)",
      },
    },
  },
  plugins: [],
};
