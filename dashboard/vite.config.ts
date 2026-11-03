import { defineConfig } from "vite";
export default defineConfig({
    base: "./",
    build: { outDir: "../src/thadam/dashboard/static", emptyOutDir: true },
    server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
