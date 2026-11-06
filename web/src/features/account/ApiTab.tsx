import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
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
import { REPO } from "@/features/shell/GithubLink";
import { formatFullDate } from "@/shared/format";
import { reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const DOCS_URL = `https://github.com/${REPO}/blob/main/docs/api.fa.md`;

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

type Health = { status: string; database: string; version: string };

const readHealth = async (path: string): Promise<Health | null> => {
	try {
		const response = await fetch(path, { headers: { Accept: "application/json" } });
		return response.ok || response.status === 503 ? ((await response.json()) as Health) : null;
	} catch {
		return null;
	}
};

function SystemInfo({
	isOpen,
	onOpenChange,
}: {
	isOpen: boolean;
	onOpenChange: (o: boolean) => void;
}) {
	const info = useQuery({
		queryKey: ["system-info"],
		queryFn: () => readHealth("/readyz"),
		enabled: isOpen,
		staleTime: 0,
	});
	const health = info.data;
	const rows: [string, string][] = [
		[
			t.acct.systemStatus,
			info.isLoading
				? t.common.loading
				: health?.status === "ok"
					? t.acct.systemOk
					: t.acct.systemDown,
		],
		[
			t.acct.systemDatabase,
			health ? (health.database === "reachable" ? t.acct.systemReachable : health.database) : "—",
		],
		[t.acct.systemVersion, health?.version ?? "—"],
		[t.acct.systemAddress, `${window.location.origin}/api/v1`],
	];
	return (
		<Modal isOpen={isOpen} onOpenChange={onOpenChange} title={t.acct.systemTitle} size="sm">
			<dl className="flex flex-col gap-3">
				{rows.map(([label, value]) => (
					<div key={label} className="flex items-center justify-between gap-4 text-sm">
						<dt className="text-muted">{label}</dt>
						<dd dir="ltr" className="break-all font-medium">
							{value}
						</dd>
					</div>
				))}
			</dl>
		</Modal>
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
			className="grid gap-3 sm:grid-cols-[1fr_12rem_auto] sm:items-end"
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
			<SelectField name="expiry" label={t.acct.keyExpiry} options={EXPIRY} />
			<SubmitButton>{t.acct.createKey}</SubmitButton>
		</FormRoot>
	);
}

/** The API: keys for programs, and the three places to read about it or look at it. */
export function ApiTab() {
	const queryClient = useQueryClient();
	const keys = useAuthListApiKeys();
	const revoke = useAuthRevokeApiKey();
	const [fresh, setFresh] = useState<string | null>(null);
	const [revoking, setRevoking] = useState<ApiKeyResponse | null>(null);
	const [system, setSystem] = useState(false);
	return (
		<div className="flex flex-col gap-5">
			<SectionCard title={t.acct.resources}>
				<div className="flex flex-wrap gap-2">
					<Button variant="secondary" onPress={() => window.open(DOCS_URL, "_blank", "noopener")}>
						{t.acct.docs}
					</Button>
					<Button variant="secondary" onPress={() => window.open("/docs", "_blank", "noopener")}>
						{t.acct.openapi}
					</Button>
					<Button variant="secondary" onPress={() => setSystem(true)}>
						{t.acct.system}
					</Button>
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
									className="flex items-center justify-between gap-3 rounded-xl border border-border p-3"
								>
									<span className="flex min-w-0 flex-col gap-0.5">
										<span className="truncate font-medium">{key.name}</span>
										<span dir="ltr" className="text-start text-xs text-muted">
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
									<Button size="sm" variant="danger-soft" onPress={() => setRevoking(key)}>
										{t.acct.revoke}
									</Button>
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
			<ConfirmDialog
				isOpen={revoking !== null}
				onOpenChange={(open) => !open && setRevoking(null)}
				title={t.acct.revoke}
				description={revoking?.name}
				confirmLabel={t.acct.revoke}
				tone="danger"
				onConfirm={async () => {
					if (!revoking) return;
					try {
						await revoke.mutateAsync({ keyId: revoking.id });
						await queryClient.invalidateQueries({ queryKey: getAuthListApiKeysQueryKey() });
						toast.success(t.acct.revoked);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
			<SystemInfo isOpen={system} onOpenChange={setSystem} />
		</div>
	);
}
