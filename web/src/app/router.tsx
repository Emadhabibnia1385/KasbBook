import { createRouter } from "@tanstack/react-router";
import { routeTree } from "@/routeTree.gen";
import { NotFound } from "./shell/NotFound";
import { PageSkeleton } from "./shell/PageSkeleton";

export const router = createRouter({
	routeTree,
	defaultPreload: "intent",
	defaultViewTransition: true,
	scrollRestoration: true,
	defaultNotFoundComponent: NotFound,
	// A slow route chunk shows the page's skeleton after a beat instead of a blank area.
	defaultPendingComponent: PageSkeleton,
	defaultPendingMs: 200,
});

declare module "@tanstack/react-router" {
	interface Register {
		router: typeof router;
	}
}
