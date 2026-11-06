import { createFileRoute } from "@tanstack/react-router";
import { ManageTabs } from "@/features/manage/ManageTabs";
import { Planning } from "@/features/planning/Planning";

export const Route = createFileRoute("/_app/planning")({ component: PlanningRoute });

function PlanningRoute() {
	return (
		<div className="flex flex-col gap-5">
			<ManageTabs />
			<Planning />
		</div>
	);
}
