import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type AnyRouter, RouterProvider } from "@tanstack/react-router";
import { NasimProvider } from "@nyxon/nasim";
import type { NasimNavigate } from "@nyxon/nasim";

// Brand blue from the logo; Nasim derives a readable accent for each scheme from it.
const ACCENT = "#1d6fd6";

type RouterLinks = { navigate: NasimNavigate; useHref: (href: string) => string };
const pairs = new WeakMap<AnyRouter, RouterLinks>();

// Nasim's links move through the TanStack router: no page load. One router gets one pair, because
// React Aria rebuilds every link when these change.
function routerLinks(router: AnyRouter): RouterLinks {
	let pair = pairs.get(router);
	if (!pair) {
		pair = {
			navigate: (href, options) => void router.navigate({ to: href, replace: options?.replace }),
			useHref: (href) => router.buildLocation({ to: href }).href,
		};
		pairs.set(router, pair);
	}
	return pair;
}

export function AppProviders({ queryClient, router }: { queryClient: QueryClient; router: AnyRouter }) {
	return (
		<QueryClientProvider client={queryClient}>
			<NasimProvider {...routerLinks(router)} defaultMode="system" accent={ACCENT}>
				<RouterProvider router={router} />
			</NasimProvider>
		</QueryClientProvider>
	);
}
