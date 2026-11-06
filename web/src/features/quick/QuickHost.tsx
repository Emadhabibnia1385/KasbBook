import { AddTransactionDialog } from "@/features/transactions/AddTransaction";
import { AddCategoryDialog } from "./AddCategoryDialog";
import { closeQuick, useQuick } from "./quickBus";

/** The dialogs the quick actions open, drawn once for the whole app. */
export function QuickHost() {
	const open = useQuick();
	return (
		<>
			<AddTransactionDialog
				isOpen={open === "transaction"}
				onOpenChange={(next) => !next && closeQuick()}
			/>
			<AddCategoryDialog
				isOpen={open === "category"}
				onOpenChange={(next) => !next && closeQuick()}
			/>
		</>
	);
}
