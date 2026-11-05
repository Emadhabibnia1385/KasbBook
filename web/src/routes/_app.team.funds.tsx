import { createFileRoute } from "@tanstack/react-router";
import { Funds } from "@/features/payroll/Funds";

export const Route = createFileRoute("/_app/team/funds")({ component: Funds });
