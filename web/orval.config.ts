import { defineConfig } from "orval";

// The API client is generated from the backend's OpenAPI document: never edit the output.
export default defineConfig({
	api: {
		input: { target: "./openapi.json" },
		hooks: { afterAllFilesWrite: "biome format --write" },
		output: {
			mode: "tags-split",
			client: "react-query",
			httpClient: "fetch",
			target: "./src/api/generated",
			schemas: "./src/api/generated/model",
			clean: true,
			formatter: "biome",
			override: {
				mutator: { path: "./src/api/transport.ts", name: "apiFetch" },
				fetch: { includeHttpResponseReturnType: false },
				query: { queryOptions: { path: "./src/api/queryDefaults.ts", name: "queryDefaults" } },
			},
		},
	},
});
