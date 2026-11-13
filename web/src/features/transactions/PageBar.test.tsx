import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PageBar } from "./PageBar";
import { savedPerPage } from "./perPage";

afterEach(() => localStorage.clear());

function bar(onPerPage = vi.fn(), perPage = 20, pageCount = 3) {
	render(
		<PageBar
			page={1}
			pageCount={pageCount}
			onPageChange={() => {}}
			perPage={perPage}
			onPerPageChange={onPerPage}
		/>,
	);
	return { box: screen.getByLabelText(/تعداد در صفحه/), onPerPage };
}

describe("the page size box", () => {
	it("takes Persian digits, clamps to the ceiling and remembers the number", () => {
		const { box, onPerPage } = bar();
		fireEvent.change(box, { target: { value: "۵۰" } });
		fireEvent.keyDown(box, { key: "Enter" });
		expect(onPerPage).toHaveBeenCalledWith(50);
		expect(savedPerPage()).toBe(50);
		fireEvent.change(box, { target: { value: "99999999" } });
		fireEvent.blur(box);
		expect(onPerPage).toHaveBeenLastCalledWith(10000);
	});

	it("puts the old number back for zero or nothing, and asks for nothing", () => {
		const { box, onPerPage } = bar();
		fireEvent.change(box, { target: { value: "0" } });
		fireEvent.blur(box);
		fireEvent.change(box, { target: { value: "" } });
		fireEvent.blur(box);
		expect(onPerPage).not.toHaveBeenCalled();
		expect((box as HTMLInputElement).value).toBe("۲۰");
	});

	it("stays when everything fits on one page, so the size can be brought back down", () => {
		bar(vi.fn(), 1000, 1);
		expect(screen.getByLabelText(/تعداد در صفحه/)).toBeTruthy();
		expect(screen.queryByText("صفحه بعد")).toBeNull();
	});

	it("offers the usual sizes in a menu", () => {
		const { onPerPage } = bar();
		const menu = screen.getByLabelText("انتخاب سریع");
		expect(Array.from((menu as HTMLSelectElement).options).map((o) => o.value)).toEqual([
			"",
			"10",
			"20",
			"30",
			"50",
			"75",
			"100",
		]);
		expect((menu as HTMLSelectElement).value).toBe("20");
		fireEvent.change(menu, { target: { value: "75" } });
		expect(onPerPage).toHaveBeenCalledWith(75);
		expect(savedPerPage()).toBe(75);
	});

	it("ignores a stored size that is not a sane number", () => {
		localStorage.setItem("kasbbook.transactionsPerPage", "abc");
		expect(savedPerPage()).toBe(20);
		localStorage.setItem("kasbbook.transactionsPerPage", "-3");
		expect(savedPerPage()).toBe(20);
	});
});
