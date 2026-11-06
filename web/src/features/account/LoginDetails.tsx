import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, FormRoot, Notice, SubmitButton, TextField, toast } from "@nyxon/nasim";
import {
	authLogin,
	authSendPasswordResetCode,
	getAuthMeQueryKey,
	useAuthSetPassword,
	useAuthSetUsername,
} from "@/api/generated/auth/auth";
import type { UserResponse } from "@/api/generated/model";
import { saveSession } from "@/api/session";
import { t } from "@/strings";

const PROVIDERS: Record<string, string> = {
	telegram: "تلگرام",
	bale: "بله",
	rubika: "روبیکا",
	eitaa: "ایتا",
};

const schema = z.object({
	username: z.string().trim().min(1, { error: t.acct.needUsername }),
	current: z.string(),
	code: z.string(),
	password: z.string().min(8, { error: t.acct.needPassword }),
});
type Values = z.input<typeof schema>;

/**
 * The username and password for signing in without Telegram. Setting a password ends every session
 * on the server, this one included, so the screen signs straight back in with what was just chosen.
 */
export function LoginDetails({ user }: { user: UserResponse }) {
	const queryClient = useQueryClient();
	const setUsername = useAuthSetUsername();
	const setPassword = useAuthSetPassword();
	// Someone who forgot the current password is sent a code on a messenger they own, which stands in for it.
	const [sentTo, setSentTo] = useState<string | null>(null);
	const [sending, setSending] = useState(false);
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { username: user.username ?? "", current: "", code: "", password: "" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				if (sentTo && !values.code.trim()) {
					form.setError("code", { message: t.acct.needCode });
					return;
				}
				try {
					const username = values.username.trim().toLowerCase();
					if (username !== user.username) {
						const saved = await setUsername.mutateAsync({ data: { username } });
						queryClient.setQueryData(getAuthMeQueryKey(), saved);
					}
					await setPassword.mutateAsync({
						data: {
							new_password: values.password,
							current_password: user.web_login_ready && !sentTo ? values.current || null : null,
							reset_code: sentTo ? values.code.trim() : null,
						},
					});
					const pair = await authLogin({ identifier: username, password: values.password });
					saveSession({
						access_token: pair.access_token,
						refresh_token: pair.refresh_token,
						expires_in: pair.expires_in,
					});
					await queryClient.invalidateQueries();
					form.reset({ username, current: "", code: "", password: "" });
					setSentTo(null);
					toast.success(t.acct.loginSaved);
				} catch (error) {
					toast.danger(error instanceof Error ? error.message : t.errors.unknown);
				}
			}}
		>
			<p className="text-sm text-muted">
				{!user.web_login_ready
					? t.acct.noPasswordYet
					: user.username
						? t.acct.hasLogin
						: t.acct.loginLead}
			</p>
			<TextField
				name="username"
				label={t.acct.username}
				description={t.acct.usernameHint}
				autoComplete="username"
				isRequired
			/>
			{user.web_login_ready ? (
				sentTo ? (
					<>
						<Notice tone="info">
							{t.acct.codeSent} {PROVIDERS[sentTo] ?? sentTo}
						</Notice>
						<TextField
							name="code"
							label={t.acct.codeLabel}
							description={t.acct.codeHint}
							autoComplete="one-time-code"
							isRequired
						/>
						<Button
							variant="ghost"
							size="sm"
							className="self-start"
							onPress={() => setSentTo(null)}
						>
							{t.acct.backToCurrent}
						</Button>
					</>
				) : (
					<>
						<TextField
							name="current"
							type="password"
							label={t.acct.currentPassword}
							autoComplete="current-password"
						/>
						<Button
							variant="ghost"
							size="sm"
							className="self-start"
							isPending={sending}
							onPress={async () => {
								setSending(true);
								try {
									const sent = await authSendPasswordResetCode();
									setSentTo(sent.sent_to);
								} catch (error) {
									toast.danger(error instanceof Error ? error.message : t.errors.unknown);
								} finally {
									setSending(false);
								}
							}}
						>
							{t.acct.forgotCurrent}
						</Button>
					</>
				)
			) : null}
			<TextField
				name="password"
				type="password"
				label={user.web_login_ready ? t.acct.newPasswordSet : t.acct.newPassword}
				description={t.acct.passwordHint}
				autoComplete="new-password"
				isRequired
			/>
			<SubmitButton>{t.acct.saveLogin}</SubmitButton>
		</FormRoot>
	);
}
