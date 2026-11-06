import { useSyncExternalStore } from "react";

// Which quick dialog is open. The button that opens one can be anywhere (the floating menu, the
// transactions page), the dialog is drawn once, by `QuickHost`, so this is the one place they meet.
export type QuickKind = "transaction" | "category" | null;

let current: QuickKind = null;
const listeners = new Set<() => void>();

function emit(next: QuickKind) {
	current = next;
	listeners.forEach((listener) => listener());
}

export const openQuick = (kind: Exclude<QuickKind, null>) => emit(kind);
export const closeQuick = () => emit(null);

export function useQuick(): QuickKind {
	return useSyncExternalStore(
		(listener) => {
			listeners.add(listener);
			return () => listeners.delete(listener);
		},
		() => current,
		() => null,
	);
}
