import { createFileRoute } from "@tanstack/react-router";
import { Transactions } from "@/features/transactions/Transactions";

export const Route = createFileRoute("/_app/transactions")({ component: Transactions });
