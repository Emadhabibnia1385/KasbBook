import { createFileRoute } from "@tanstack/react-router";
import { ManageTabs } from "@/features/manage/ManageTabs";
import { Wallet } from "@/features/wallet/Wallet";

export const Route = createFileRoute("/_app/wallet")({ component: WalletRoute });

function WalletRoute() {
	return (
		<div className="flex flex-col gap-5">
			<ManageTabs />
			<Wallet />
		</div>
	);
}
