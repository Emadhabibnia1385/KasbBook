import { renderSVG } from "uqr";

// A QR for the sign-in link, so a desktop visitor can finish on the phone that has Telegram.
export function qrcodeToSvg(text: string): string {
	return renderSVG(text, { border: 1, ecc: "M" });
}
