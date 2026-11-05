import { tanstackRouter } from "@tanstack/router-plugin/vite";
import babel from "@rolldown/plugin-babel";
import tailwindcss from "@tailwindcss/vite";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import Icons from "unplugin-icons/vite";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import { serviceWorker } from "./scripts/serviceWorkerPlugin.ts";

// The API runs beside the panel in production (one origin); in dev it is proxied from here.
const API = process.env.VITE_DEV_API_TARGET ?? "http://127.0.0.1:8210";

export default defineConfig({
	// The router plugin must come before the React plugin (TanStack Router docs).
	plugins: [
		tanstackRouter({ target: "react", autoCodeSplitting: true }),
		react(),
		babel({ presets: [reactCompilerPreset()] }),
		tailwindcss(),
		Icons({ compiler: "jsx", jsx: "react", autoInstall: false }),
		serviceWorker(),
	],
	resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
	server: { proxy: { "/api": { target: API, changeOrigin: true } } },
});
