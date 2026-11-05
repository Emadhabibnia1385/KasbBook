import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { FormRoot, NumberField, SubmitButton, SwitchField, toast } from "@nyxon/nasim";
import { getAuthMeQueryKey, useAuthUpdateProfile } from "@/api/generated/auth/auth";
import type { UserResponse } from "@/api/generated/model";
import { t } from "@/strings";

// The ranges are the server's rule; these only save a round trip and keep the keyboard honest.
const schema = z.object({
	enabled: z.boolean(),
	hour: z.number().int().min(0).max(23),
	days: z.number().int().min(0).max(60),
});
type Values = z.input<typeof schema>;

/** The daily digest and the reminder lead time, the same settings the bot's reminders screen holds. */
export function DigestForm({ user }: { user: UserResponse }) {
	const queryClient = useQueryClient();
	const update = useAuthUpdateProfile();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			enabled: user.digest_enabled,
			hour: user.digest_hour,
			days: user.reminder_days,
		},
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				try {
					const saved = await update.mutateAsync({
						data: {
							digest_enabled: values.enabled,
							digest_hour: values.hour,
							reminder_days: values.days,
						},
					});
					queryClient.setQueryData(getAuthMeQueryKey(), saved);
					form.reset(values);
					toast.success(t.digest.saved);
				} catch (error) {
					toast.danger(error instanceof Error ? error.message : t.errors.unknown);
				}
			}}
		>
			<p className="text-sm text-muted">{t.digest.lead}</p>
			<SwitchField name="enabled" label={t.digest.enabled} />
			<NumberField
				name="hour"
				label={t.digest.hour}
				description={t.digest.hourHint}
				minValue={0}
				maxValue={23}
			/>
			<NumberField
				name="days"
				label={t.digest.days}
				description={t.digest.daysHint}
				minValue={0}
				maxValue={60}
			/>
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}
