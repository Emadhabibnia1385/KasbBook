import { createFileRoute } from "@tanstack/react-router";
import { PeriodDetail } from "@/features/payroll/PeriodDetail";

export const Route = createFileRoute("/_app/team/periods/$periodId")({ component: PeriodRoute });

function PeriodRoute() {
	const { periodId } = Route.useParams();
	return <PeriodDetail periodId={periodId} />;
}
