import { createFileRoute } from "@tanstack/react-router";
import { ManageOverview } from "@/features/manage/ManageOverview";

export const Route = createFileRoute("/_app/manage")({ component: ManageOverview });
