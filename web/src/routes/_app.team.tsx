import { createFileRoute } from "@tanstack/react-router";
import { TeamLayout } from "@/features/payroll/TeamLayout";

export const Route = createFileRoute("/_app/team")({ component: TeamLayout });
