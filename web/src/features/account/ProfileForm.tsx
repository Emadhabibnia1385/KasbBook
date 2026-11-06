import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { FormRoot, SelectField, SubmitButton, TextField, toast } from "@nyxon/nasim";
import { getAuthMeQueryKey, useAuthUpdateProfile } from "@/api/generated/auth/auth";
import type { UserResponse } from "@/api/generated/model";
import { t } from "@/strings";
import { zoneOptions } from "./timezones";

const schema = z.object({
	name: z.string().trim().min(1, { error: t.acct.needName }).max(120),
	timezone: z.string().min(1),
});
type Values = z.input<typeof schema>;

/** The name and the time zone. The zone starts from the browser's and can be changed by hand. */
export function ProfileForm({ user }: { user: UserResponse }) {
	const queryClient = useQueryClient();
	const update = useAuthUpdateProfile();
	const options = useMemo(() => zoneOptions(user.timezone), [user.timezone]);
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { name: user.display_name, timezone: user.timezone },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				try {
					const saved = await update.mutateAsync({
						data: { display_name: values.name.trim(), timezone: values.timezone },
					});
					queryClient.setQueryData(getAuthMeQueryKey(), saved);
					// A zone chosen by hand is the person's word; the browser's guess must not replace it.
					rememberManualZone();
					form.reset(values);
					toast.success(t.acct.saved);
				} catch (error) {
					toast.danger(error instanceof Error ? error.message : t.errors.unknown);
				}
			}}
		>
			<TextField name="name" label={t.acct.name} isRequired />
			<SelectField
				name="timezone"
				label={t.acct.timezone}
				description={t.acct.timezoneHint}
				options={options}
			/>
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

export const ZONE_KEY = "kasbbook.zone";

function rememberManualZone() {
	try {
		localStorage.setItem(ZONE_KEY, "manual");
	} catch {
		// the guess may run again next visit; that is all
	}
}
