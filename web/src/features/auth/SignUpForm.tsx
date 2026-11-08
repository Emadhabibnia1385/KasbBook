import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { FormRoot, Notice, SubmitButton, TextField } from "@nyxon/nasim";
import { authRegister } from "@/api/generated/auth/auth";
import { toAscii } from "@/shared/format";
import { t } from "@/strings";

const USERNAME = /^[A-Za-z][A-Za-z0-9_.]{2,31}$/;

// A username and the password twice; nothing else is asked. The name is also what is shown until the
// person changes it, and an email or a messenger can be added later from «حساب من».
const schema = z
	.object({
		username: z
			.string()
			.transform((value) => toAscii(value).trim())
			.refine((value) => USERNAME.test(value), { error: t.signup.badUsername }),
		password: z.string().min(8, { error: t.signup.shortPassword }),
		confirm: z.string(),
	})
	.refine((values) => values.password === values.confirm, {
		path: ["confirm"],
		error: t.signup.mismatch,
	});
type Values = z.input<typeof schema>;

type Pair = { access_token: string; refresh_token: string; expires_in: number };

export function SignUpForm({
	onDone,
	problem,
	setProblem,
}: {
	onDone: (pair: Pair) => void;
	problem: string | null;
	setProblem: (message: string | null) => void;
}) {
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { username: "", password: "", confirm: "" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-3 text-start"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				setProblem(null);
				try {
					onDone(
						await authRegister({
							username: values.username,
							password: values.password,
							password_confirm: values.confirm,
						}),
					);
				} catch (error) {
					setProblem(error instanceof Error ? error.message : t.errors.unknown);
				}
			}}
		>
			<TextField
				name="username"
				label={t.signup.username}
				description={t.signup.usernameHint}
				dir="ltr"
				autoComplete="username"
				isRequired
			/>
			<TextField
				name="password"
				type="password"
				label={t.signup.password}
				description={t.signup.passwordHint}
				autoComplete="new-password"
				isRequired
			/>
			<TextField
				name="confirm"
				type="password"
				label={t.signup.confirm}
				autoComplete="new-password"
				isRequired
			/>
			<Notice tone="info">{t.signup.note}</Notice>
			{problem ? (
				<Notice tone="danger" role="alert">
					{problem}
				</Notice>
			) : null}
			<SubmitButton>{t.signup.submit}</SubmitButton>
		</FormRoot>
	);
}
