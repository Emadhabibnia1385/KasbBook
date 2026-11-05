import { createFileRoute } from "@tanstack/react-router";
import { Team } from "@/features/team/Team";

export const Route = createFileRoute("/_app/team")({ component: Team });
