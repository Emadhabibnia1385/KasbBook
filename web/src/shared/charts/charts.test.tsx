import { render, screen, within } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it } from "vitest";
import { media } from "@/test/setup";
import { Donut } from "./Donut";
import { GroupedColumns } from "./Columns";
import { StackedColumns } from "./StackedColumns";
import { useReducedMotion } from "./useReducedMotion";

const format = (value: string) => `${value} تومان`;

const stacked = (
	<StackedColumns
		title="دسته‌ها در ماه"
		summary="سهم هر دسته از جمع ماه"
		rowHeader="ماه"
		formatValue={format}
		total={{ key: "total", name: "جمع" }}
		parts={[
			{ key: "rent", name: "اجاره", color: "var(--accent)" },
			{ key: "ads", name: "تبلیغات", color: "var(--success)" },
		]}
		rows={[
			{
				key: "m1",
				label: "مهر",
				values: { rent: "4000000.0000", ads: "1200000.5000", total: "5200000.5000" },
			},
			{ key: "m2", label: "آبان", values: { rent: "0.0000", ads: "300.0000", total: "300.0000" } },
		]}
	/>
);

// jsdom has no layout, so contrast cannot be computed here: that one rule is switched off, and the
// contrast of the tokens is checked where they are defined, not in a chart's test.
async function violations(container: HTMLElement) {
	const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
	return result.violations.map((v) => `${v.id}: ${v.help}`);
}

describe("charts", () => {
	it("names the picture for a screen reader and shows every part in a legend", () => {
		render(stacked);
		expect(screen.getByRole("img", { name: "سهم هر دسته از جمع ماه" })).toBeInTheDocument();
		const legend = screen.getByRole("list", { name: /./ });
		expect(within(legend).getByText("اجاره")).toBeInTheDocument();
		expect(within(legend).getByText("تبلیغات")).toBeInTheDocument();
	});

	it("keeps the exact figures in a table, as the API sent them", () => {
		render(stacked);
		const table = screen.getByRole("table");
		expect(within(table).getByText("4000000.0000 تومان")).toBeInTheDocument();
		expect(within(table).getByText("5200000.5000 تومان")).toBeInTheDocument();
		expect(within(table).getAllByRole("row")).toHaveLength(3);
	});

	it("says so instead of drawing an empty plot", () => {
		render(
			<StackedColumns
				title="خالی"
				summary="s"
				rowHeader="ماه"
				formatValue={format}
				emptyText="داده‌ای نیست"
				parts={[{ key: "a", name: "الف", color: "var(--accent)" }]}
				rows={[{ key: "m", label: "مهر", values: { a: "0.0000" } }]}
			/>,
		);
		expect(screen.getByText("داده‌ای نیست")).toBeInTheDocument();
		expect(screen.queryByRole("img")).toBeNull();
	});

	it("lists each donut slice with its share and exact amount", () => {
		render(
			<Donut
				title="سهم دسته‌ها"
				summary="سهم‌ها"
				formatValue={format}
				slices={[
					{ key: "a", label: "اجاره", value: "750.0000", color: "var(--accent)" },
					{ key: "b", label: "حمل", value: "250.0000", color: "var(--success)" },
				]}
			/>,
		);
		const table = screen.getByRole("table");
		expect(within(table).getByText("750.0000 تومان")).toBeInTheDocument();
		expect(within(table).getByText("حمل")).toBeInTheDocument();
	});

	it("passes the accessibility checks that jsdom can run", async () => {
		const { container } = render(
			<div>
				{stacked}
				<GroupedColumns
					title="درآمد و هزینه"
					summary="شش ماه"
					rowHeader="ماه"
					formatValue={format}
					bars={[{ key: "income", name: "درآمد", color: "var(--success)" }]}
					rows={[{ key: "m", label: "مهر", values: { income: "10.0000" } }]}
				/>
			</div>,
		);
		expect(await violations(container)).toEqual([]);
	});
});

describe("reduced motion", () => {
	function Probe() {
		return <span data-testid="reduced">{String(useReducedMotion())}</span>;
	}

	it("follows the system setting", () => {
		media.reduced = true;
		render(<Probe />);
		expect(screen.getByTestId("reduced")).toHaveTextContent("true");
	});

	it("animates when nobody asked for less", () => {
		media.reduced = false;
		render(<Probe />);
		expect(screen.getByTestId("reduced")).toHaveTextContent("false");
	});
});
