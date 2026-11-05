// Telegram opens a Mini App with the signed launch data in the address hash. Reading it from there needs
// no script from telegram.org; the server checks the signature, so nothing here is trusted.
export function miniAppInitData(): string | null {
	try {
		return new URLSearchParams(location.hash.slice(1)).get("tgWebAppData") || null;
	} catch {
		return null;
	}
}
