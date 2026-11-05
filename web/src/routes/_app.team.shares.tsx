import { createFileRoute } from "@tanstack/react-router";
import { Shares } from "@/features/payroll/Shares";

export const Route = createFileRoute("/_app/team/shares")({ component: Shares });
