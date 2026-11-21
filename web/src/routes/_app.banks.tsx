import { createFileRoute } from "@tanstack/react-router";
import { Banks } from "@/features/banks/Banks";
import { ManageTabs } from "@/features/manage/ManageTabs";

export const Route = createFileRoute("/_app/banks")({ component: BanksRoute });

function BanksRoute() {
	return (
		<div className="flex flex-col gap-5">
			<ManageTabs />
			<Banks />
		</div>
	);
}
