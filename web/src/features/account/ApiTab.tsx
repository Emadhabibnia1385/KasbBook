import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	CopyField,
	FormRoot,
	Modal,
	SectionCard,
	SelectField,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	getAuthListApiKeysQueryKey,
	useAuthCreateApiKey,
	useAuthListApiKeys,
	useAuthRevokeApiKey,
} from "@/api/generated/auth/auth";
import type { ApiKeyResponse } from "@/api/generated/model";
import { formatFullDate } from "@/shared/format";
import { reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const EXPIRY = [
	{ value: "never", label: t.acct.never },
	{ value: "30", label: t.acct.days30 },
	{ value: "90", label: t.acct.days90 },
	{ value: "365", label: t.acct.days365 },
];

const schema = z.object({
	name: z.string().trim().min(1, { error: t.acct.keyNameHint }).max(80),
	expiry: z.string(),
});
type Values = z.input<typeof schema>;

type Health = { status: string; database: string };

const readHealth = async (): Promise<Health | null> => {
	try {
		const response = await fetch("/readyz", { headers: { Accept: "application/json" } });
		return response.ok || response.status === 503 ? ((await response.json()) as Health) : null;
	} catch {
		return null;
	}
};

/** The service's health, in the open at the top of the page: no button to press to see it. */
function Status() {
	const info = useQuery({
		queryKey: ["system-info"],
		queryFn: readHealth,
		refetchInterval: 60_000,
	});
	const health = info.data;
	const ok = health?.status === "ok";
	const database = health
		? health.database === "reachable"
			? t.acct.systemReachable
			: health.database
		: "—";
	const dot = (good: boolean) => (
		<span aria-hidden className={`size-2 rounded-full ${good ? "bg-success" : "bg-danger"}`} />
	);
	return (
		<div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
			<span className="flex items-center gap-2">
				{info.isLoading ? null : dot(ok)}
				<span className="text-muted">{t.acct.systemStatus}:</span>
				<b>{info.isLoading ? t.common.loading : ok ? t.acct.systemOk : t.acct.systemDown}</b>
			</span>
			<span className="flex items-center gap-2">
				<span className="text-muted">{t.acct.systemDatabase}:</span>
				<b>{info.isLoading ? "…" : database}</b>
			</span>
		</div>
	);
}

function CreateKey({ onCreated }: { onCreated: (key: string) => void }) {
	const queryClient = useQueryClient();
	const create = useAuthCreateApiKey();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { name: "", expiry: "never" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-3"
			onSubmit={async (values) => {
				try {
					const made = await create.mutateAsync({
						data: {
							name: values.name.trim(),
							expires_in_days: values.expiry === "never" ? null : Number(values.expiry),
						},
					});
					await queryClient.invalidateQueries({ queryKey: getAuthListApiKeysQueryKey() });
					form.reset();
					onCreated(made.key);
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<TextField name="name" label={t.acct.keyName} placeholder={t.acct.keyNameHint} isRequired />
			<div className="grid grid-cols-[1fr_auto] items-end gap-3">
				<SelectField name="expiry" label={t.acct.keyExpiry} options={EXPIRY} />
				<SubmitButton>{t.acct.createKey}</SubmitButton>
			</div>
		</FormRoot>
	);
}

/** The API: where it lives and how to read about it, then the keys programs use to reach it. */
export function ApiTab() {
	const queryClient = useQueryClient();
	const keys = useAuthListApiKeys();
	const remove = useAuthRevokeApiKey();
	const [fresh, setFresh] = useState<string | null>(null);
	const [busy, setBusy] = useState<string | null>(null);

	// A key is deleted on the press: it stops working at once and leaves the list.
	const deleteKey = async (key: ApiKeyResponse) => {
		setBusy(key.id);
		try {
			await remove.mutateAsync({ keyId: key.id });
			await queryClient.invalidateQueries({ queryKey: getAuthListApiKeysQueryKey() });
			toast.success(t.acct.revoked);
		} catch (error) {
			reportFailure(error);
		} finally {
			setBusy(null);
		}
	};

	const origin = window.location.origin;
	return (
		<div className="flex flex-col gap-5">
			<SectionCard title={t.acct.resources}>
				<div className="flex flex-col gap-4">
					<Status />
					{/* Every address is the one this panel itself is served from, so a self-hosted copy on its own
					    domain or a bare IP points at itself and nothing is written into the code. */}
					<CopyField label={t.acct.systemAddress} value={`${origin}/api/v1`} />
					<CopyField label={t.acct.docsAddress} value={`${origin}/docs`} />
					<CopyField label={t.acct.openapiAddress} value={`${origin}/openapi.json`} />
					<div className="grid grid-cols-2 gap-3">
						<Button variant="secondary" onPress={() => window.open("/docs", "_blank", "noopener")}>
							{t.acct.docs}
						</Button>
						<Button
							variant="secondary"
							onPress={() => window.open("/openapi.json", "_blank", "noopener")}
						>
							{t.acct.openapi}
						</Button>
					</div>
				</div>
			</SectionCard>
			<SectionCard title={t.acct.keys} description={t.acct.keysLead}>
				<div className="flex flex-col gap-4">
					<CreateKey onCreated={setFresh} />
					{(keys.data ?? []).length === 0 ? (
						<p className="text-sm text-muted">{t.acct.noKeys}</p>
					) : (
						<ul className="flex flex-col gap-2">
							{(keys.data ?? []).map((key) => (
								<li
									key={key.id}
									className="flex items-center gap-3 rounded-xl border border-border p-3"
								>
									<Button
										size="sm"
										variant="danger-soft"
										isPending={busy === key.id}
										onPress={() => void deleteKey(key)}
									>
										{t.common.delete}
									</Button>
									<span className="flex min-w-0 flex-1 flex-col gap-0.5 text-left">
										<span className="truncate font-medium">{key.name}</span>
										<span dir="ltr" className="text-xs text-muted">
											{key.prefix}…
										</span>
										<span className="text-xs text-muted">
											{key.last_used_at
												? `${t.acct.keyLastUsed}: ${formatFullDate(key.last_used_at.slice(0, 10))}`
												: t.acct.keyNever}
											{key.expires_at
												? ` · ${t.acct.keyExpires}: ${formatFullDate(key.expires_at.slice(0, 10))}`
												: ""}
										</span>
									</span>
								</li>
							))}
						</ul>
					)}
				</div>
			</SectionCard>
			<Modal
				isOpen={fresh !== null}
				onOpenChange={(open) => !open && setFresh(null)}
				title={t.acct.keyCreatedTitle}
				size="md"
			>
				<div className="flex flex-col gap-3">
					<p className="text-sm text-muted">{t.acct.keyCreatedBody}</p>
					{fresh ? <CopyField label={t.acct.keyField} value={fresh} /> : null}
				</div>
			</Modal>
		</div>
	);
}
