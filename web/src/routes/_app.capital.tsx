import { createFileRoute } from "@tanstack/react-router";
import { Capital } from "@/features/capital/Capital";

export const Route = createFileRoute("/_app/capital")({ component: Capital });
