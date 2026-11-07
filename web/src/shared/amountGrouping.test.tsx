import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { NasimProvider, TextField } from "@nyxon/nasim";

function Harness() {
	const [value, setValue] = useState("");
	return (
		<NasimProvider>
			<TextField label="مبلغ" inputMode="decimal" value={value} onChange={setValue} />
			<output data-testid="value">{value}</output>
		</NasimProvider>
	);
}

describe("an amount box", () => {
	it("shows a separator every three digits but keeps the plain digits", () => {
		render(<Harness />);
		const box = screen.getByLabelText("مبلغ");
		fireEvent.change(box, { target: { value: "1234567" } });
		expect(box).toHaveValue("1,234,567");
		expect(screen.getByTestId("value")).toHaveTextContent("1234567");
	});

	it("takes a typed separator back out and leaves the decimals alone", () => {
		render(<Harness />);
		const box = screen.getByLabelText("مبلغ");
		fireEvent.change(box, { target: { value: "12345.67891" } });
		expect(box).toHaveValue("12,345.67891");
		fireEvent.change(box, { target: { value: "1,2345.67891" } });
		expect(box).toHaveValue("12,345.67891");
		expect(screen.getByTestId("value")).toHaveTextContent("12345.67891");
	});

	it("groups Persian digits too and shows a typo as typed", () => {
		render(<Harness />);
		const box = screen.getByLabelText("مبلغ");
		fireEvent.change(box, { target: { value: "۱۲۳۴۵۶" } });
		expect(box).toHaveValue("۱۲۳,۴۵۶");
		fireEvent.change(box, { target: { value: "12ab3456" } });
		expect(box).toHaveValue("12ab3456");
	});

	it("keeps the caret after the digit just typed when separators move", () => {
		render(<Harness />);
		const box = screen.getByLabelText("مبلغ") as HTMLInputElement;
		box.focus();
		fireEvent.change(box, { target: { value: "1234" } });
		expect(box).toHaveValue("1,234");
		// What a browser does: the text changes and the caret sits after the digit just typed.
		const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
		setter?.call(box, "1,2934");
		box.setSelectionRange(4, 4);
		fireEvent.input(box);
		expect(box).toHaveValue("12,934");
		expect(box.selectionStart).toBe(4);
	});
});
