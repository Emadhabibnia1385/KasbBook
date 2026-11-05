import { createFileRoute } from "@tanstack/react-router";
import { Reports } from "@/features/reports/Reports";

export const Route = createFileRoute("/_app/reports")({ component: Reports });
