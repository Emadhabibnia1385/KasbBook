import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";

// Kept apart from vite.config.ts on purpose: the panel's build plugins (router codegen, service worker,
// compiler) have nothing to do with a test and only slow it. The alias is the one thing both share.
export default defineConfig({
	resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
	test: {
		projects: [
			{
				extends: true,
				test: { name: "node", environment: "node", include: ["src/**/*.test.ts"] },
			},
			{
				// Components: rendered for real in jsdom, so what a screen reader is told is what is asserted.
				extends: true,
				test: {
					name: "jsdom",
					environment: "jsdom",
					include: ["src/**/*.test.tsx"],
					setupFiles: ["./src/test/setup.ts"],
				},
			},
		],
	},
});
