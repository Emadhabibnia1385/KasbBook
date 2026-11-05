import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Button, ConfirmDialog, Notice, toast } from "@nyxon/nasim";
import {
	getBooksListAttachmentsQueryKey,
	useBooksAddAttachment,
	useBooksDeleteAttachment,
	useBooksListAttachments,
} from "@/api/generated/books/books";
import type { AttachmentResponse } from "@/api/generated/model";
import { formatAmount } from "@/shared/format";
import { t } from "@/strings";
import { FileProblem, MAX_FILES, prepareFile, sizeText, useAttachmentUrl } from "./attachments";

const problemText = (error: unknown) =>
	error instanceof FileProblem
		? error.message === "pdf too big"
			? t.attach.pdfTooBig
			: error.message === "type"
				? t.attach.badType
				: t.attach.tooBig
		: error instanceof Error && error.message
			? error.message
			: t.errors.unknown;

/** One stored file: a thumbnail for a photo, an icon for a PDF; opens in a new tab. */
export function AttachmentItem({
	bookId,
	transactionId,
	file,
	onRemove,
}: {
	bookId: string;
	transactionId: string;
	file: AttachmentResponse;
	onRemove?: () => void;
}) {
	const isImage = file.content_type.startsWith("image/");
	const url = useAttachmentUrl(bookId, transactionId, file.id, isImage);
	return (
		<li className="flex items-center gap-3 rounded-xl border border-border p-2">
			{isImage && url ? (
				<img src={url} alt="" className="size-12 shrink-0 rounded-lg object-cover" />
			) : (
				<span
					aria-hidden
					className="grid size-12 shrink-0 place-items-center rounded-lg bg-default text-xs font-semibold text-muted"
				>
					{file.content_type === "application/pdf" ? "PDF" : "…"}
				</span>
			)}
			<span className="flex min-w-0 flex-1 flex-col">
				<span dir="ltr" className="truncate text-start text-sm font-medium">
					{file.file_name}
				</span>
				<span className="text-xs text-muted">{sizeText(file.size)}</span>
			</span>
			<Button
				size="sm"
				variant="secondary"
				onPress={async () => {
					// A new tab needs the bytes under the person's own sign-in, so they are fetched here first.
					const { apiFetch } = await import("@/api/transport");
					try {
						const blob = await apiFetch<Blob>(
							`/api/v1/books/${bookId}/transactions/${transactionId}/attachments/${file.id}`,
						);
						window.open(URL.createObjectURL(blob), "_blank", "noopener");
					} catch (error) {
						toast.danger(problemText(error));
					}
				}}
			>
				{t.attach.open}
			</Button>
			{onRemove ? (
				<Button size="sm" variant="ghost" onPress={onRemove}>
					{t.common.delete}
				</Button>
			) : null}
		</li>
	);
}

/**
 * Attach photos and PDFs. With a transaction (editing) a file is sent as soon as it is chosen; without
 * one (recording) the files wait in `queue` and the form sends them once the transaction exists.
 */
export function AttachmentsField({
	bookId,
	transactionId,
	queue,
	onQueue,
}: {
	bookId: string;
	transactionId?: string;
	queue: File[];
	onQueue: (files: File[]) => void;
}) {
	const queryClient = useQueryClient();
	const input = useRef<HTMLInputElement>(null);
	const list = useBooksListAttachments(bookId, transactionId ?? "", {
		query: { enabled: Boolean(transactionId) },
	});
	const add = useBooksAddAttachment();
	const remove = useBooksDeleteAttachment();
	const [busy, setBusy] = useState(false);
	const [problem, setProblem] = useState<string | null>(null);
	const [removing, setRemoving] = useState<AttachmentResponse | null>(null);
	const stored = list.data ?? [];
	const total = stored.length + queue.length;

	const choose = async (picked: FileList | null) => {
		if (!picked?.length) return;
		setProblem(null);
		setBusy(true);
		const added: File[] = [];
		try {
			const room = MAX_FILES - total;
			if (picked.length > room) setProblem(t.attach.tooMany);
			for (const original of Array.from(picked).slice(0, Math.max(0, room))) {
				try {
					const ready = await prepareFile(original);
					if (transactionId) {
						await add.mutateAsync({ bookId, transactionId, data: { file: ready } });
						await queryClient.invalidateQueries({
							queryKey: getBooksListAttachmentsQueryKey(bookId, transactionId),
						});
						await queryClient.invalidateQueries({
							queryKey: [`/api/v1/books/${bookId}/transactions`],
						});
					} else {
						added.push(ready);
					}
				} catch (error) {
					setProblem(problemText(error));
				}
			}
			if (added.length) onQueue([...queue, ...added]);
		} finally {
			setBusy(false);
			if (input.current) input.current.value = "";
		}
	};

	return (
		<div className="flex flex-col gap-2">
			<span className="text-sm font-medium">{t.attach.title}</span>
			{stored.length || queue.length ? (
				<ul className="flex flex-col gap-2" aria-label={t.attach.title}>
					{transactionId
						? stored.map((file) => (
								<AttachmentItem
									key={file.id}
									bookId={bookId}
									transactionId={transactionId}
									file={file}
									onRemove={() => setRemoving(file)}
								/>
							))
						: null}
					{queue.map((file, index) => (
						<li
							key={`${file.name}-${index}`}
							className="flex items-center gap-3 rounded-xl border border-border p-2"
						>
							<span
								aria-hidden
								className="grid size-12 shrink-0 place-items-center rounded-lg bg-default text-xs font-semibold text-muted"
							>
								{file.type === "application/pdf" ? "PDF" : "IMG"}
							</span>
							<span className="flex min-w-0 flex-1 flex-col">
								<span dir="ltr" className="truncate text-start text-sm font-medium">
									{file.name}
								</span>
								<span className="text-xs text-muted">{sizeText(file.size)}</span>
							</span>
							<Button
								size="sm"
								variant="ghost"
								onPress={() => onQueue(queue.filter((_, i) => i !== index))}
							>
								{t.common.delete}
							</Button>
						</li>
					))}
				</ul>
			) : (
				<p className="text-xs text-muted">{t.attach.hint}</p>
			)}
			{problem ? (
				<Notice tone="warning" role="alert">
					{problem}
				</Notice>
			) : null}
			<input
				ref={input}
				type="file"
				multiple
				// Photos from the camera or the gallery, and PDF invoices.
				accept="image/*,application/pdf"
				className="sr-only"
				tabIndex={-1}
				aria-hidden
				onChange={(event) => void choose(event.target.files)}
			/>
			<Button
				variant="secondary"
				className="self-start"
				isPending={busy}
				isDisabled={total >= MAX_FILES}
				onPress={() => input.current?.click()}
			>
				{t.attach.add} ({formatAmount(total)}/{formatAmount(MAX_FILES)})
			</Button>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.attach.removeTitle}
				description={removing?.file_name}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing || !transactionId) return;
					await remove.mutateAsync({ bookId, transactionId, attachmentId: removing.id });
					await queryClient.invalidateQueries({
						queryKey: getBooksListAttachmentsQueryKey(bookId, transactionId),
					});
					await queryClient.invalidateQueries({
						queryKey: [`/api/v1/books/${bookId}/transactions`],
					});
				}}
			/>
		</div>
	);
}
