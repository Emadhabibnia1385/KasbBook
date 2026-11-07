import { BookRequired } from "@/features/books/BookRequired";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	EmptyState,
	ErrorState,
	FormRoot,
	Modal,
	Notice,
	PageHeader,
	PageSkeleton,
	SectionCard,
	SelectField,
	StatusChip,
	SubmitButton,
	SwitchField,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	getBooksListMembersQueryKey,
	useBooksAddMember,
	useBooksAddPerson,
	useBooksLinkPerson,
	useBooksListMembers,
	useBooksRemoveMember,
	useBooksUpdateMember,
} from "@/api/generated/books/books";
import type { BookResponse, MemberResponse, ShareResponse } from "@/api/generated/model";
import {
	usePayrollClearShare,
	usePayrollListShares,
	usePayrollSetShare,
} from "@/api/generated/payroll/payroll";
import { useActiveBook } from "@/features/books/useActiveBook";
import { fromUnits, isPositive, plain, sum, toUnits } from "@/features/payroll/decimal";
import {
	refreshPayroll,
	reportError,
	shareBasisLabel,
	shareValueText,
} from "@/features/payroll/shared";
import { ActionMenu, Figure, ItemCard, type MenuItem } from "@/features/payroll/ui";
import { isPayrollBook } from "@/features/payroll/shared";
import { formatAmount, formatFullDate, formatMoney, toAscii } from "@/shared/format";
import { t } from "@/strings";

const ROLES = (["admin", "accountant", "member", "viewer"] as const).map((value) => ({
	value,
	label: `${t.team.roles[value]} — ${t.team.roleHints[value]}`,
}));
const roleLabel = (role: string) => (t.team.roles as Record<string, string>)[role] ?? role;

// The bot offers these five; `project` exists on the server but nothing measures it yet.
const BASES = (["percent", "fixed", "hours", "days", "points"] as const).map((value) => ({
	value,
	label: t.payroll.shareBasis[value],
}));

function valueCopy(basis: string) {
	if (basis === "percent")
		return { label: t.payroll.shares.valuePercent, hint: t.payroll.shares.hintPercent };
	if (basis === "fixed")
		return { label: t.payroll.shares.valueFixed, hint: t.payroll.shares.hintFixed };
	return { label: t.payroll.shares.valueWeight, hint: t.payroll.shares.hintWeight };
}

// A percentage, a weight and an amount are all plain numbers here: «۵۰م» is not fifty million percent.
const validValue = (value: string) => /^\d+(\.\d{1,4})?$/.test(value) && isPositive(value);

// ------------------------------------------------------------------ share
const shareSchema = z.object({
	basis: z
		.string({ error: t.payroll.shares.needBasis })
		.min(1, { error: t.payroll.shares.needBasis }),
	value: z.string().transform(toAscii).refine(validValue, { error: t.payroll.shares.badValue }),
});
type ShareValues = z.input<typeof shareSchema>;

function ShareForm({
	book,
	member,
	current,
	onDone,
}: {
	book: BookResponse;
	member: MemberResponse;
	current?: ShareResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const setShare = usePayrollSetShare();
	const form = useForm<ShareValues>({
		resolver: zodResolver(shareSchema),
		defaultValues: {
			basis: current?.basis ?? "percent",
			value: current ? plain(current.value) : "",
		},
	});
	const copy = valueCopy(useWatch({ control: form.control, name: "basis" }));
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = shareSchema.parse(raw);
				try {
					await setShare.mutateAsync({
						bookId: book.id,
						data: { user_id: member.user_id, basis: values.basis, value: values.value },
					});
					await refreshPayroll(queryClient, book.id);
					toast.success(t.payroll.saved);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<SelectField
				name="basis"
				label={t.payroll.shares.basis}
				description={t.payroll.shares.basisHelp}
				options={BASES}
			/>
			<TextField
				name="value"
				label={copy.label}
				description={copy.hint}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

function Summary({ shares }: { shares: readonly ShareResponse[] }) {
	const percents = shares.filter((share) => share.basis === "percent").map((share) => share.value);
	if (percents.length === 0) return null;
	const total = sum(percents);
	const rest = fromUnits(100n * 10_000n - toUnits(total));
	if (toUnits(total) > 100n * 10_000n)
		return (
			<Notice tone="warning" title={`${t.payroll.shares.percentTotal}: ${formatAmount(total)}٪`}>
				{t.payroll.shares.over}
			</Notice>
		);
	if (toUnits(total) < 100n * 10_000n)
		return (
			<Notice tone="info" title={`${t.payroll.shares.percentTotal}: ${formatAmount(total)}٪`}>
				{t.payroll.shares.under} {formatAmount(rest)}٪
			</Notice>
		);
	return null;
}

// ------------------------------------------------------------------ add
const addSchema = z
	.object({
		access: z.boolean(),
		name: z.string().trim(),
		identifier: z.string().trim(),
		role: z.string(),
		basis: z.string(),
		value: z.string().transform(toAscii),
	})
	.superRefine((values, context) => {
		if (values.access) {
			if (!values.identifier)
				context.addIssue({ code: "custom", path: ["identifier"], message: t.team.needIdentifier });
		} else if (!values.name) {
			context.addIssue({ code: "custom", path: ["name"], message: t.team.needName });
		}
		if (values.value && !validValue(values.value))
			context.addIssue({ code: "custom", path: ["value"], message: t.payroll.shares.badValue });
	});
type AddValues = z.input<typeof addSchema>;

function AddMember({
	book,
	payroll,
	onDone,
}: {
	book: BookResponse;
	payroll: boolean;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const addPerson = useBooksAddPerson();
	const addAccount = useBooksAddMember();
	const setShare = usePayrollSetShare();
	const form = useForm<AddValues>({
		resolver: zodResolver(addSchema),
		defaultValues: {
			access: false,
			name: "",
			identifier: "",
			role: "member",
			basis: "percent",
			value: "",
		},
	});
	const access = useWatch({ control: form.control, name: "access" });
	const copy = valueCopy(useWatch({ control: form.control, name: "basis" }));
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = addSchema.parse(raw);
				try {
					const added = values.access
						? await addAccount.mutateAsync({
								bookId: book.id,
								data: { identifier: values.identifier, role: values.role },
							})
						: await addPerson.mutateAsync({
								bookId: book.id,
								data: { name: values.name, role: "viewer" },
							});
					await queryClient.invalidateQueries({ queryKey: getBooksListMembersQueryKey(book.id) });
					if (payroll && values.value) {
						try {
							await setShare.mutateAsync({
								bookId: book.id,
								data: { user_id: added.user_id, basis: values.basis, value: values.value },
							});
						} catch (error) {
							// The person is in; only the share failed, and it can be set from their card.
							reportError(error);
						}
						await refreshPayroll(queryClient, book.id);
					}
					toast.success(t.team.invited);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			{access ? (
				<>
					<TextField
						name="identifier"
						label={t.team.identifier}
						description={t.team.identifierHint}
						dir="ltr"
						isRequired
					/>
					<SelectField
						name="role"
						label={t.team.role}
						description={t.team.roleHelp}
						options={ROLES}
					/>
				</>
			) : (
				<TextField name="name" label={t.team.name} description={t.team.nameHint} isRequired />
			)}
			<SwitchField
				name="access"
				label={t.team.hasAccess}
				description={access ? undefined : t.team.hasAccessHint}
			/>
			{payroll ? (
				<div className="flex flex-col gap-4 rounded-xl border border-border p-3">
					<div>
						<p className="text-sm font-medium">{t.team.shareOptional}</p>
						<p className="text-xs text-muted">{t.team.shareLater}</p>
					</div>
					<SelectField name="basis" label={t.payroll.shares.basis} options={BASES} />
					<TextField
						name="value"
						label={copy.label}
						description={copy.hint}
						inputMode="decimal"
						dir="ltr"
					/>
				</div>
			) : null}
			<SubmitButton>{t.team.send}</SubmitButton>
		</FormRoot>
	);
}

// ------------------------------------------------------------------ small edits
const nameSchema = z.object({ name: z.string().trim().min(1, { error: t.team.needName }) });
type NameValues = z.input<typeof nameSchema>;

function EditName({
	book,
	member,
	onDone,
}: {
	book: BookResponse;
	member: MemberResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const update = useBooksUpdateMember();
	const form = useForm<NameValues>({
		resolver: zodResolver(nameSchema),
		defaultValues: { name: member.display_name },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				try {
					await update.mutateAsync({
						bookId: book.id,
						memberUserId: member.user_id,
						data: { display_name: values.name },
					});
					await Promise.all([
						queryClient.invalidateQueries({ queryKey: getBooksListMembersQueryKey(book.id) }),
						refreshPayroll(queryClient, book.id),
					]);
					toast.success(t.team.nameSaved);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<TextField name="name" label={t.team.name} description={t.team.nameHint} isRequired />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

const roleSchema = z.object({ role: z.string({ error: t.team.needRole }) });
type RoleValues = z.input<typeof roleSchema>;

function EditRole({
	book,
	member,
	onDone,
}: {
	book: BookResponse;
	member: MemberResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const update = useBooksUpdateMember();
	const form = useForm<RoleValues>({
		resolver: zodResolver(roleSchema),
		defaultValues: { role: member.role },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				try {
					await update.mutateAsync({
						bookId: book.id,
						memberUserId: member.user_id,
						data: { role: values.role },
					});
					await queryClient.invalidateQueries({ queryKey: getBooksListMembersQueryKey(book.id) });
					toast.success(t.team.roleSaved);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<SelectField name="role" label={t.team.role} description={t.team.roleHelp} options={ROLES} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

const linkSchema = z.object({
	identifier: z.string().trim().min(1, { error: t.team.needIdentifier }),
	role: z.string({ error: t.team.needRole }),
});
type LinkValues = z.input<typeof linkSchema>;

function LinkAccount({
	book,
	member,
	onDone,
}: {
	book: BookResponse;
	member: MemberResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const link = useBooksLinkPerson();
	const form = useForm<LinkValues>({
		resolver: zodResolver(linkSchema),
		defaultValues: { identifier: "", role: "member" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				try {
					await link.mutateAsync({
						bookId: book.id,
						memberUserId: member.user_id,
						data: { identifier: values.identifier, role: values.role },
					});
					await Promise.all([
						queryClient.invalidateQueries({ queryKey: getBooksListMembersQueryKey(book.id) }),
						refreshPayroll(queryClient, book.id),
					]);
					toast.success(t.team.linked);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<p className="text-sm text-muted">{t.team.linkBody}</p>
			<TextField
				name="identifier"
				label={t.team.identifier}
				description={t.team.identifierHint}
				dir="ltr"
				isRequired
			/>
			<SelectField name="role" label={t.team.role} description={t.team.roleHelp} options={ROLES} />
			<SubmitButton>{t.team.link}</SubmitButton>
		</FormRoot>
	);
}

// ------------------------------------------------------------------ the page
type Action = "share" | "name" | "role" | "link" | "clear" | "remove";

function MemberMenu({
	member,
	hasShare,
	showShare,
	onAction,
}: {
	member: MemberResponse;
	hasShare: boolean;
	showShare: boolean;
	onAction: (action: Action) => void;
}) {
	const owner = member.role === "owner";
	const items: MenuItem[] = [
		...(member.has_account === false
			? [
					{ id: "name", label: t.team.editName },
					{ id: "link", label: t.team.link },
				]
			: []),
		...(owner ? [] : [{ id: "role", label: t.team.changeRole }]),
		...(showShare && hasShare
			? [{ id: "clear", label: t.payroll.shares.clear, danger: true }]
			: []),
		...(owner ? [] : [{ id: "remove", label: t.team.remove, danger: true }]),
	];
	return (
		<ActionMenu
			label={`${t.team.menu}: ${member.display_name}`}
			items={items}
			onAction={(id) => onAction(id as Action)}
		/>
	);
}

function Members({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const payroll = isPayrollBook(book);
	const members = useBooksListMembers(book.id);
	const shares = usePayrollListShares(book.id, { query: { enabled: payroll } });
	const clear = usePayrollClearShare();
	const remove = useBooksRemoveMember();
	const [adding, setAdding] = useState(false);
	const [target, setTarget] = useState<{ member: MemberResponse; action: Action } | null>(null);

	if (members.isLoading || (payroll && shares.isLoading)) return <PageSkeleton rows={3} />;
	if (members.isError) return <ErrorState onRetry={() => void members.refetch()} />;

	// Someone who may see the team but not its pay gets the list without the shares, rather than an error.
	const showShare = payroll && !shares.isError;
	const rules = new Map((shares.data ?? []).map((share) => [share.user_id, share]));
	const money = (value: string) => formatMoney(value, book.currency);
	const people = members.data ?? [];
	const close = () => setTarget(null);

	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.team.title}
				description={book.name}
				actions={<Button onPress={() => setAdding(true)}>{t.team.invite}</Button>}
			/>
			{showShare ? <Summary shares={shares.data ?? []} /> : null}
			<SectionCard title={t.team.members} description={showShare ? t.team.lead : t.team.leadSolo}>
				{people.length === 0 ? (
					<EmptyState title={t.payroll.noMembers} />
				) : (
					<ul className="grid gap-3 md:grid-cols-2">
						{people.map((member) => {
							const rule = rules.get(member.user_id);
							const account = member.has_account !== false;
							return (
								<ItemCard
									key={member.user_id}
									title={member.display_name}
									aside={
										<MemberMenu
											member={member}
											hasShare={rule !== undefined}
											showShare={showShare}
											onAction={(action) => setTarget({ member, action })}
										/>
									}
									actions={
										showShare ? (
											<Button
												size="sm"
												variant={rule ? "secondary" : "primary"}
												onPress={() => setTarget({ member, action: "share" })}
											>
												{rule ? t.payroll.shares.change : t.payroll.shares.set}
											</Button>
										) : undefined
									}
								>
									<div className="flex flex-wrap gap-2">
										{account ? (
											<StatusChip
												tone={member.role === "owner" ? "info" : "neutral"}
												label={roleLabel(member.role)}
											/>
										) : null}
										<StatusChip
											tone={account ? "success" : "warning"}
											label={account ? t.team.withAccount : t.team.withoutAccount}
										/>
									</div>
									{showShare ? (
										rule ? (
											<p className="text-sm">
												<Figure>{shareValueText(rule.basis, rule.value, money)}</Figure>
												<span className="text-muted">
													{" · "}
													{shareBasisLabel(rule.basis)}
													{" · "}
													{t.payroll.shares.since} {formatFullDate(rule.effective_from)}
												</span>
											</p>
										) : (
											<p className="text-sm text-muted">{t.payroll.shares.unset}</p>
										)
									) : null}
									{account ? null : <p className="text-xs text-muted">{t.team.noAccountHint}</p>}
								</ItemCard>
							);
						})}
					</ul>
				)}
			</SectionCard>

			<Modal isOpen={adding} onOpenChange={setAdding} title={t.team.invite} size="sm">
				<AddMember book={book} payroll={payroll} onDone={() => setAdding(false)} />
			</Modal>
			<Modal
				isOpen={target?.action === "share"}
				onOpenChange={(open) => !open && close()}
				title={`${t.payroll.shares.formTitle} ${target?.member.display_name ?? ""}`}
				size="sm"
			>
				{target?.action === "share" ? (
					<ShareForm
						key={target.member.user_id}
						book={book}
						member={target.member}
						current={rules.get(target.member.user_id)}
						onDone={close}
					/>
				) : null}
			</Modal>
			<Modal
				isOpen={target?.action === "name"}
				onOpenChange={(open) => !open && close()}
				title={t.team.editNameTitle}
				size="sm"
			>
				{target?.action === "name" ? (
					<EditName key={target.member.user_id} book={book} member={target.member} onDone={close} />
				) : null}
			</Modal>
			<Modal
				isOpen={target?.action === "role"}
				onOpenChange={(open) => !open && close()}
				title={`${t.team.roleTitle}: ${target?.member.display_name ?? ""}`}
				size="sm"
			>
				{target?.action === "role" ? (
					<EditRole key={target.member.user_id} book={book} member={target.member} onDone={close} />
				) : null}
			</Modal>
			<Modal
				isOpen={target?.action === "link"}
				onOpenChange={(open) => !open && close()}
				title={`${t.team.linkTitle}: ${target?.member.display_name ?? ""}`}
				size="sm"
			>
				{target?.action === "link" ? (
					<LinkAccount
						key={target.member.user_id}
						book={book}
						member={target.member}
						onDone={close}
					/>
				) : null}
			</Modal>
			<ConfirmDialog
				isOpen={target?.action === "clear"}
				onOpenChange={(open) => !open && close()}
				title={t.payroll.shares.clearTitle}
				description={`${target?.member.display_name ?? ""}. ${t.payroll.shares.clearBody}`}
				confirmLabel={t.payroll.shares.clear}
				tone="danger"
				onConfirm={async () => {
					if (!target) return;
					try {
						await clear.mutateAsync({ bookId: book.id, memberUserId: target.member.user_id });
						await refreshPayroll(queryClient, book.id);
						toast.success(t.payroll.shares.cleared);
					} catch (error) {
						reportError(error);
						throw error;
					}
				}}
			/>
			<ConfirmDialog
				isOpen={target?.action === "remove"}
				onOpenChange={(open) => !open && close()}
				title={t.team.removeTitle}
				description={`${target?.member.display_name ?? ""}. ${t.team.removeBody}`}
				confirmLabel={t.team.remove}
				tone="danger"
				onConfirm={async () => {
					if (!target) return;
					try {
						await remove.mutateAsync({ bookId: book.id, memberUserId: target.member.user_id });
						await Promise.all([
							queryClient.invalidateQueries({ queryKey: getBooksListMembersQueryKey(book.id) }),
							refreshPayroll(queryClient, book.id),
						]);
						toast.success(t.team.removed);
					} catch (error) {
						reportError(error);
						throw error;
					}
				}}
			/>
		</div>
	);
}

export function Team() {
	const { book, isLoading } = useActiveBook();
	if (isLoading) return <PageSkeleton />;
	if (!book) return <BookRequired />;
	return <Members book={book} />;
}
