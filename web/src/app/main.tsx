import { QueryClient } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/index.css";
import { watchInstallPrompt } from "@/features/pwa/install";
import { AppProviders } from "./providers";
import { registerWorker } from "./registerWorker";
import { router } from "./router";

const queryClient = new QueryClient({
	defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
});

// The browser offers its install prompt once, and may do it before the install button is on screen.
watchInstallPrompt();

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root");

createRoot(root).render(
	<StrictMode>
		<AppProviders queryClient={queryClient} router={router} />
	</StrictMode>,
);
registerWorker();
