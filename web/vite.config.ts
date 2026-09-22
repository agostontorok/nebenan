import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "./",
  build: {
    rollupOptions: {
      input: {
        hub: resolve(__dirname, "index.html"),
        darmstadt: resolve(__dirname, "darmstadt/index.html"),
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});