import type { ReactNode } from "react";

/** One group of settings inside a larger card: a heading, a line of explanation, then the controls. */
export function SettingGroup({
	title,
	description,
	children,
}: {
	title: string;
	description?: string | undefined;
	children: ReactNode;
}) {
	return (
		<section className="flex flex-col gap-2 border-b border-separator py-5 first:pt-0 last:border-b-0 last:pb-0">
			<div className="flex flex-col gap-0.5">
				<h3 className="text-base font-semibold">{title}</h3>
				{description ? <p className="text-sm text-muted">{description}</p> : null}
			</div>
			{children}
		</section>
	);
}
