import { createFileRoute } from "@tanstack/react-router";
import { Books } from "@/features/books/Books";

export const Route = createFileRoute("/_app/books")({ component: Books });
