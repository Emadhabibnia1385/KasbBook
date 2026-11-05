import { useEffect, useState } from "react";
import { apiFetch } from "@/api/transport";

// The same limit the server enforces; a photo is shrunk to fit before it is sent.
export const MAX_BYTES = 1_500_000;
export const MAX_FILES = 5;
const MAX_SIDE = 1600;

export class FileProblem extends Error {}

function load(file: File): Promise<HTMLImageElement> {
	return new Promise((resolve, reject) => {
		const url = URL.createObjectURL(file);
		const image = new Image();
		image.onload = () => {
			URL.revokeObjectURL(url);
			resolve(image);
		};
		image.onerror = () => {
			URL.revokeObjectURL(url);
			reject(new FileProblem("not an image"));
		};
		image.src = url;
	});
}

function toBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob | null> {
	return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
}

/**
 * A phone's photo is several megabytes and the server takes 1.5. Photos are redrawn smaller as JPEG
 * (a receipt is read, not printed), stepping the quality down until they fit; a PDF cannot be
 * shrunk here, so a big one is refused with its size. GIFs are left alone unless too big.
 */
export async function prepareFile(file: File): Promise<File> {
	const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
	if (isPdf) {
		if (file.size > MAX_BYTES) throw new FileProblem("pdf too big");
		return file;
	}
	if (!file.type.startsWith("image/")) throw new FileProblem("type");
	if (file.size <= MAX_BYTES && file.type !== "image/heic" && file.type !== "image/heif") {
		if (
			file.type === "image/jpeg" ||
			file.type === "image/png" ||
			file.type === "image/webp" ||
			file.type === "image/gif"
		) {
			if (file.size <= 400_000) return file;
		}
	}
	const image = await load(file);
	const scale = Math.min(1, MAX_SIDE / Math.max(image.naturalWidth, image.naturalHeight));
	const canvas = document.createElement("canvas");
	canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
	canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
	const context = canvas.getContext("2d");
	if (!context) throw new FileProblem("canvas");
	// JPEG has no transparency: a transparent PNG would turn black.
	context.fillStyle = "#fff";
	context.fillRect(0, 0, canvas.width, canvas.height);
	context.drawImage(image, 0, 0, canvas.width, canvas.height);
	for (const quality of [0.85, 0.72, 0.6, 0.48, 0.36]) {
		const blob = await toBlob(canvas, quality);
		if (blob && blob.size <= MAX_BYTES) {
			const name = file.name.replace(/\.[^.]+$/, "") || "photo";
			return new File([blob], `${name}.jpg`, { type: "image/jpeg" });
		}
	}
	throw new FileProblem("too big");
}

/** A stored file as an object URL, fetched with the person's own sign-in (an <img> tag cannot send it). */
export function useAttachmentUrl(
	bookId: string,
	transactionId: string,
	attachmentId: string,
	enabled = true,
) {
	const [url, setUrl] = useState<string | null>(null);
	useEffect(() => {
		if (!enabled) return;
		let revoked = false;
		let made: string | null = null;
		apiFetch<Blob>(
			`/api/v1/books/${bookId}/transactions/${transactionId}/attachments/${attachmentId}`,
		)
			.then((blob) => {
				if (revoked) return;
				made = URL.createObjectURL(blob);
				setUrl(made);
			})
			.catch(() => setUrl(null));
		return () => {
			revoked = true;
			if (made) URL.revokeObjectURL(made);
		};
	}, [bookId, transactionId, attachmentId, enabled]);
	return url;
}

export const sizeText = (bytes: number) =>
	bytes < 1024 * 1024
		? `${Math.max(1, Math.round(bytes / 1024))} KB`
		: `${(bytes / 1024 / 1024).toFixed(1)} MB`;
