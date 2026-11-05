import { createFileRoute } from "@tanstack/react-router";
import { Planning } from "@/features/planning/Planning";

export const Route = createFileRoute("/_app/planning")({ component: Planning });
