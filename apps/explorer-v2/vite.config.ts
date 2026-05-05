import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/explorer-react/",
  plugins: [react()],
  server: {
    port: 4174,
  },
});
