import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "v2-root-redirect",
      configureServer(server) {
        server.middlewares.use((req, _res, next) => {
          if (req.url === "/" || req.url === "/index.html") req.url = "/index-v2.html";
          next();
        });
      },
    },
  ],
  root: ".",
  build: {
    outDir: "dist-v2",
    rollupOptions: { input: "./index-v2.html" },
  },
  server: {
    port: 5174,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
