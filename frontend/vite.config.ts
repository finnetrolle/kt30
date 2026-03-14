import { fileURLToPath, URL } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";

function normalizeBasePath(rawValue: string | undefined) {
  const trimmed = (rawValue ?? "").trim();

  if (!trimmed || trimmed === "/") {
    return "/";
  }

  return `/${trimmed.replace(/^\/+|\/+$/g, "")}/`;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  const base = normalizeBasePath(env.VITE_APP_BASE_PATH || env.FRONTEND_ROUTE_PREFIX || "app");

  return {
    base,
    envDir: "..",
    plugins: [react()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url))
      }
    },
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true
        },
        "/health": {
          target: "http://localhost:8000",
          changeOrigin: true
        },
        "/ready": {
          target: "http://localhost:8000",
          changeOrigin: true
        }
      }
    }
  };
});
