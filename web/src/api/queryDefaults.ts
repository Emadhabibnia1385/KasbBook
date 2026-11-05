import { ApiError } from "./transport";

// A 4xx is the server's answer and repeats if asked again; anything else is tried twice more.
export function retryTransient(failures: number, error: unknown): boolean {
	if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
	return failures < 2;
}

/** What every query starts from; a hand-written one spreads it. */
export const DEFAULT_QUERY_OPTIONS = {
	staleTime: 30_000,
	retry: retryTransient,
	refetchOnWindowFocus: false,
} as const;

/** The defaults of every generated query (Orval mutator); a call's own options win. */
export function queryDefaults<T extends object>(options: T): T {
	return { ...DEFAULT_QUERY_OPTIONS, ...options };
}
