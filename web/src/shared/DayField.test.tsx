import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { NasimProvider } from "@nyxon/nasim";
import { DayField } from "./DayField";

function Harness({ start = "" }: { start?: string }) {
	const [value, setValue] = useState(start);
	return (
		<NasimProvider>
			<DayField label="از تاریخ" value={value} onChange={setValue} />
			<output data-testid="value">{value}</output>
		</NasimProvider>
	);
}

describe("DayField", () => {
	it("turns a typed Jalali day into the picker value, with no time of its own", () => {
		render(<Harness />);
		fireEvent.change(screen.getByLabelText("از تاریخ"), { target: { value: "۱۴۰۵/۰۸/۱۵" } });
		expect(screen.getByTestId("value")).toHaveTextContent("2026-11-06T12:00");
	});

	it("tells a day that does not exist from one still being typed", () => {
		render(<Harness />);
		const box = screen.getByLabelText("از تاریخ");
		fireEvent.change(box, { target: { value: "1405/08/" } });
		expect(screen.queryByText(/فقط این‌قدر روز/)).toBeNull();
		fireEvent.change(box, { target: { value: "1405/07/31" } });
		expect(screen.getByText(/فقط این‌قدر روز دارد: 30/)).toBeInTheDocument();
		expect(screen.getByTestId("value")).toHaveTextContent("");
	});

	it("shows an existing value in the Jalali calendar", () => {
		render(<Harness start="2026-03-21T12:00" />);
		expect(screen.getByLabelText("از تاریخ")).toHaveValue("۱۴۰۵/۰۱/۰۱");
	});

	it("fills the day from a quick chip", () => {
		render(<Harness />);
		fireEvent.click(screen.getByRole("button", { name: "امروز" }));
		expect(screen.getByTestId("value").textContent).toMatch(/^\d{4}-\d{2}-\d{2}T12:00$/);
	});
});
