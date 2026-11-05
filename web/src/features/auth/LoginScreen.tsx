import { useMemo } from "react";
import { qrcodeToSvg } from "./qr";
import { Button, Notice, Spinner } from "@nyxon/nasim";
import { TelegramIcon } from "@/shared/icons";
import { t } from "@/strings";
import { useTelegramLogin } from "./useTelegramLogin";

// The only way in: Telegram vouches for the person, and the device remembers it.
export function LoginScreen({ onDone }: { onDone: () => void }) {
	const { state, begin, cancel } = useTelegramLogin(onDone);
	const link = state.phase === "waiting" ? state.deepLink : null;
	const qr = useMemo(() => (link ? qrcodeToSvg(link) : null), [link]);

	// Opening the link in the same gesture as the press keeps pop-up blockers quiet.
	const start = async () => {
		const target = await begin();
		if (target) window.open(target, "_blank", "noopener");
	};

	return (
		<main className="grid min-h-dvh place-items-center bg-background px-page py-10 text-foreground">
			<div className="flex w-full max-w-sm flex-col items-center gap-6 text-center">
				<img src="/icons/icon-192.png" alt="" className="size-24" />
				<div className="flex flex-col gap-2">
					<h1 className="text-2xl font-bold">{t.login.title}</h1>
					<p className="text-sm text-muted">{t.login.lead}</p>
				</div>

				{state.phase === "failed" ? <Notice tone="danger" role="alert">{state.message}</Notice> : null}

				{link ? (
					<div className="flex w-full flex-col items-center gap-4 rounded-2xl border border-border bg-surface p-5">
						<div className="flex items-center gap-2 font-medium">
							<Spinner size="sm" />
							{t.login.waitingTitle}
						</div>
						<p className="text-sm text-muted">{t.login.waiting}</p>
						<Button variant="secondary" onPress={() => window.open(link, "_blank", "noopener")}>
							<TelegramIcon aria-hidden />
							{t.login.openAgain}
						</Button>
						{qr ? (
							<figure className="flex flex-col items-center gap-2">
								<div aria-hidden className="size-40 rounded-xl bg-white p-2 [&>svg]:size-full" dangerouslySetInnerHTML={{ __html: qr }} />
								<figcaption className="text-xs text-muted">{t.login.scan}</figcaption>
							</figure>
						) : null}
						<Button variant="ghost" onPress={cancel}>
							{t.login.cancel}
						</Button>
					</div>
				) : (
					<Button size="lg" className="w-full" isPending={state.phase === "starting"} onPress={() => void start()}>
						<TelegramIcon aria-hidden />
						{state.phase === "starting" ? t.login.opening : t.login.button}
					</Button>
				)}
				<p className="text-xs text-muted">{t.login.remembered}</p>
			</div>
		</main>
	);
}
