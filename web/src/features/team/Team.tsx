import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, EmptyState, FormRoot, Modal, PageHeader, PageSkeleton, SectionCard, SelectField, StatusChip, SubmitButton, TextField, toast } from "@nyxon/nasim";
import { getBooksListMembersQueryKey, useBooksAddMember, useBooksListMembers } from "@/api/generated/books/books";
import type { BookResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { t } from "@/strings";

const ROLES = [
	{ value: "admin", label: t.team.roles.admin },
	{ value: "accountant", label: t.team.roles.accountant },
	{ value: "member", label: t.team.roles.member },
	{ value: "viewer", label: t.team.roles.viewer },
];
const roleLabel = (role: string) => (t.team.roles as Record<string, string>)[role] ?? role;

const schema = z.object({
	identifier: z.string().trim().min(1, { error: t.team.needIdentifier }),
	role: z.string({ error: t.team.needRole }),
});
type Values = z.input<typeof schema>;

function Members({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const { data = [], isLoading } = useBooksListMembers(book.id);
	const invite = useBooksAddMember();
	const [adding, setAdding] = useState(false);
	const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { identifier: "", role: "member" } });
	if (isLoading) return <PageSkeleton header={false} rows={3} />;
	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.nav.team} description={book.name} actions={<Button onPress={() => setAdding(true)}>{t.team.invite}</Button>} />
			<SectionCard title={t.team.members}>
				<ul className="flex flex-col gap-2">
					{data.map((member) => (
						<li key={member.user_id} className="flex items-center justify-between rounded-xl border border-border p-3">
							<span className="font-medium">{member.display_name}</span>
							<StatusChip tone={member.role === "owner" ? "info" : "neutral"} label={roleLabel(member.role)} />
						</li>
					))}
				</ul>
			</SectionCard>
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.team.invite} size="sm">
				<FormRoot
					form={form}
					className="flex flex-col gap-4"
					onSubmit={async (values) => {
						try {
							await invite.mutateAsync({ bookId: book.id, data: { identifier: values.identifier, role: values.role } });
							await queryClient.invalidateQueries({ queryKey: getBooksListMembersQueryKey(book.id) });
							toast.success(t.team.invited);
							form.reset();
							setAdding(false);
						} catch (error) {
							toast.danger(error instanceof Error ? error.message : t.errors.unknown);
						}
					}}
				>
					<TextField name="identifier" label={t.team.identifier} description={t.team.identifierHint} dir="ltr" isRequired />
					<SelectField name="role" label={t.team.role} options={ROLES} />
					<SubmitButton>{t.team.send}</SubmitButton>
				</FormRoot>
			</Modal>
		</div>
	);
}

export function Team() {
	const { book, isLoading } = useActiveBook();
	if (isLoading) return <PageSkeleton />;
	if (!book) return <EmptyState as="h1" title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />;
	return <Members book={book} />;
}
