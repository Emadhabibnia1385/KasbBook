import { createFileRoute } from "@tanstack/react-router";
import { Portfolio } from "@/features/portfolio/Portfolio";

export const Route = createFileRoute("/_app/portfolio")({ component: Portfolio });
