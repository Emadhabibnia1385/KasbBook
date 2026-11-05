import { createFileRoute } from "@tanstack/react-router";
import { Recurring } from "@/features/recurring/Recurring";

export const Route = createFileRoute("/_app/recurring")({ component: Recurring });
