import { useState } from "react";
import { Button, Modal } from "@nyxon/nasim";
import { InstallIcon } from "@/shared/icons";
import { t } from "@/strings";
import { promptInstall, useInstallState } from "./install";

// Offers the install the browser allows: its own prompt where there is one, and the Share-sheet
// steps on iPhone and iPad, where Safari has no prompt to call.
export function InstallButton() {
	const state = useInstallState();
	const [help, setHelp] = useState(false);
	if (state === "installed" || state === "none") return null;
	return (
		<>
			<Button
				variant="secondary"
				className="justify-center"
				onPress={() => (state === "prompt" ? void promptInstall() : setHelp(true))}
			>
				<InstallIcon aria-hidden />
				{t.common.install}
			</Button>
			<Modal isOpen={help} onOpenChange={setHelp} title={t.install.iosTitle} size="xs">
				<ol className="flex list-decimal flex-col gap-2 ps-5 text-sm">
					{t.install.iosSteps.map((step) => (
						<li key={step}>{step}</li>
					))}
				</ol>
			</Modal>
		</>
	);
}
