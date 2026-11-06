import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	FormRoot,
	Notice,
	Spinner,
	SubmitButton,
	TextField,
} from "@nyxon/nasim";
import { authDemo, authGuest, authLogin } from "@/api/generated/auth/auth";
import { saveSession } from "@/api/session";
import { DeveloperFooter } from "@/features/shell/DeveloperFooter";
import { TelegramIcon } from "@/shared/icons";
import { t } from "@/strings";
import { qrcodeToSvg } from "./qr";
import { useTelegramLogin } from "./useTelegramLogin";

const schema = z.object({
	username: z.string().trim().min(1, { error: t.signin.needBoth }),
	password: z.string().min(1, { error: t.signin.needBoth }),
});
type Values = z.input<typeof schema>;

function Divider({ children }: { children: string }) {
	return (
		<div className="flex items-center gap-3 text-xs text-muted">
			<span className="h-px flex-1 bg-border" />
			<span>{children}</span>
			<span className="h-px flex-1 bg-border" />
		</div>
	);
}

// Three ways in: Telegram vouches for the person; a username and password; or a guest with nothing kept.
export function LoginScreen({ onDone }: { onDone: () => void }) {
	const queryClient = useQueryClient();
	const { state, begin, cancel } = useTelegramLogin(onDone);
	const link = state.phase === "waiting" ? state.deepLink : null;
	const qr = useMemo(() => (link ? qrcodeToSvg(link) : null), [link]);
	const [problem, setProblem] = useState<string | null>(null);
	const [askingGuest, setAskingGuest] = useState(false);
	const [makingDemo, setMakingDemo] = useState(false);
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { username: "", password: "" },
	});

	// Opening the link in the same gesture as the press keeps pop-up blockers quiet.
	const start = async () => {
		const target = await begin();
		if (target) window.open(target, "_blank", "noopener");
	};

	const enter = (pair: { access_token: string; refresh_token: string; expires_in: number }) => {
		saveSession(pair);
		queryClient.clear();
		onDone();
	};

	return (
		<main className="flex min-h-dvh flex-col bg-background text-foreground">
			<div className="grid flex-1 place-items-center px-page py-10">
				<div className="flex w-full max-w-sm flex-col items-center gap-6 text-center">
					<img src="/icons/icon-192.png" alt="" className="size-24" />
					<div className="flex flex-col gap-2">
						<h1 className="text-2xl font-bold">{t.login.title}</h1>
						<p className="text-sm text-muted">{t.login.lead}</p>
					</div>

					{state.phase === "failed" ? (
						<Notice tone="danger" role="alert">
							{state.message}
						</Notice>
					) : null}

					<div className="flex w-full flex-col gap-4 rounded-2xl border border-border bg-surface p-5">
						{link ? (
							<div className="flex w-full flex-col items-center gap-4">
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
										<div
											aria-hidden
											className="size-40 rounded-xl bg-white p-2 [&>svg]:size-full"
											dangerouslySetInnerHTML={{ __html: qr }}
										/>
										<figcaption className="text-xs text-muted">{t.login.scan}</figcaption>
									</figure>
								) : null}
								<Button variant="ghost" onPress={cancel}>
									{t.login.cancel}
								</Button>
							</div>
						) : (
							<Button
								size="lg"
								className="w-full"
								isPending={state.phase === "starting"}
								onPress={() => void start()}
							>
								<TelegramIcon aria-hidden />
								{state.phase === "starting" ? t.login.opening : t.login.button}
							</Button>
						)}

						<Divider>{t.signin.or}</Divider>

						<FormRoot
							form={form}
							className="flex flex-col gap-3 text-start"
							onSubmit={async (values) => {
								setProblem(null);
								try {
									enter(
										await authLogin({
											identifier: values.username.trim(),
											password: values.password,
										}),
									);
								} catch (error) {
									setProblem(error instanceof Error ? error.message : t.errors.unknown);
								}
							}}
						>
							<TextField
								name="username"
								label={t.signin.username}
								autoComplete="username"
								autoFocus={false}
							/>
							<TextField
								name="password"
								type="password"
								label={t.signin.password}
								autoComplete="current-password"
							/>
							{problem ? (
								<Notice tone="danger" role="alert">
									{problem}
								</Notice>
							) : null}
							<SubmitButton>{t.signin.submit}</SubmitButton>
						</FormRoot>

						<Divider>{t.guest.divider}</Divider>
						<Button variant="outline" className="w-full" onPress={() => setAskingGuest(true)}>
							{t.guest.button}
						</Button>
						<Button
							variant="secondary"
							className="w-full"
							isPending={makingDemo}
							onPress={async () => {
								setMakingDemo(true);
								setProblem(null);
								try {
									enter(await authDemo());
								} catch (error) {
									setProblem(error instanceof Error ? error.message : t.errors.unknown);
									setMakingDemo(false);
								}
							}}
						>
							{makingDemo ? t.guest.demoMaking : t.guest.demoButton}
						</Button>
						<p className="text-center text-xs text-muted">{t.guest.demoHint}</p>
					</div>
				</div>
			</div>
			<DeveloperFooter />
			<ConfirmDialog
				isOpen={askingGuest}
				onOpenChange={setAskingGuest}
				title={t.guest.title}
				description={t.guest.body}
				confirmLabel={t.guest.confirm}
				onConfirm={async () => {
					try {
						enter(await authGuest());
					} catch (error) {
						setProblem(error instanceof Error ? error.message : t.errors.unknown);
					}
				}}
			/>
		</main>
	);
}
