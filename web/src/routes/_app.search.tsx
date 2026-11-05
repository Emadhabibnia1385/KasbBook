import { createFileRoute } from "@tanstack/react-router";
import { Search } from "@/features/search/Search";

export const Route = createFileRoute("/_app/search")({ component: Search });
