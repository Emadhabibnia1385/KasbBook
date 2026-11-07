import { Collapsible } from "@nyxon/nasim";
import { t } from "@/strings";

const g = t.payroll.guide;

function Block({ title, children }: { title: string; children: React.ReactNode }) {
	return (
		<section className="flex flex-col gap-2">
			<h3 className="text-sm font-semibold">{title}</h3>
			{children}
		</section>
	);
}

/** Money in, money out: how a period's income becomes a share, a slip and a payment, written once and in plain words. */
export function PayrollGuide() {
	return (
		<Collapsible title={g.title} description={g.lead}>
			<Block title={g.flowTitle}>
				<ol className="flex flex-col gap-2 ps-5 text-sm [list-style:decimal]">
					{g.flowSteps.map((step) => (
						<li key={step} className="text-pretty">
							{step}
						</li>
					))}
				</ol>
				<p className="text-xs text-muted">{g.flowNote}</p>
			</Block>

			<Block title={g.chooseTitle}>
				<ul className="grid gap-2 md:grid-cols-2">
					{g.choose.map((item) => (
						<li key={item.title} className="rounded-xl border border-border p-3 text-sm">
							<p className="font-medium">{item.title}</p>
							<p className="text-muted">{item.when}</p>
							<p>{item.how}</p>
						</li>
					))}
				</ul>
			</Block>

			<Block title={g.weightTitle}>
				<p className="text-sm text-pretty">{g.weightBody}</p>
				<div className="rounded-xl bg-default p-3 text-sm">
					<p className="font-medium">{g.weightExampleTitle}</p>
					<ul className="mt-1 flex flex-col gap-1">
						{g.weightExample.map((line) => (
							<li key={line}>{line}</li>
						))}
					</ul>
				</div>
			</Block>

			<Block title={g.cutsTitle}>
				<ul className="flex flex-col gap-2 ps-5 text-sm [list-style:disc]">
					{g.cuts.map((line) => (
						<li key={line} className="text-pretty">
							{line}
						</li>
					))}
				</ul>
			</Block>
		</Collapsible>
	);
}
