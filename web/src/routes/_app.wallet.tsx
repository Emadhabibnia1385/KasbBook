import { createFileRoute } from "@tanstack/react-router";
import { Wallet } from "@/features/wallet/Wallet";

export const Route = createFileRoute("/_app/wallet")({ component: Wallet });
