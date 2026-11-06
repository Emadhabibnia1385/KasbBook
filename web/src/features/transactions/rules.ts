import { z } from "zod";
import { toAscii } from "@/shared/format";
import { t } from "@/strings";

/** An amount as typed: ASCII or Persian digits, up to four decimals, above zero. */
export const amountRule = z
	.string()
	.transform(toAscii)
	.refine((value) => /^\d+(\.\d{1,4})?$/.test(value) && Number(value) > 0, {
		error: t.transactions.badAmount,
	});
