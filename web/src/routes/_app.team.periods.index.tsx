import { createFileRoute } from "@tanstack/react-router";
import { Periods } from "@/features/payroll/Periods";

export const Route = createFileRoute("/_app/team/periods/")({ component: Periods });
