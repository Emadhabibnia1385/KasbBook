import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { NasimProvider } from "@nyxon/nasim";
import { SignUpForm } from "./SignUpForm";

const register = vi.fn();
vi.mock("@/api/generated/auth/auth", () => ({ authRegister: (...args: unknown[]) => register(...args) }));

function setup() {
	const done = vi.fn();
	render(
		<NasimProvider>
			<SignUpForm onDone={done} problem={null} setProblem={() => {}} />
		</NasimProvider>,
	);
	return done;
}

const fill = (name: RegExp, value: string) =>
	fireEvent.change(screen.getByLabelText(name), { target: { value } });

describe("SignUpForm", () => {
	it("holds the two passwords to each other before it asks the server anything", async () => {
		register.mockReset();
		setup();
		fill(/نام کاربری/, "emad_h");
		fill(/^رمز/, "a-good-password");
		fill(/تکرار رمز/, "another-password");
		fireEvent.click(screen.getByRole("button", { name: "ساخت حساب" }));
		expect(await screen.findByText("رمز و تکرارش یکی نیستند")).toBeInTheDocument();
		expect(register).not.toHaveBeenCalled();
	});

	it("sends the username and both passwords, and hands back the session", async () => {
		register.mockReset();
		register.mockResolvedValue({ access_token: "a", refresh_token: "r", expires_in: 60 });
		const done = setup();
		fill(/نام کاربری/, "Emad_H");
		fill(/^رمز/, "a-good-password");
		fill(/تکرار رمز/, "a-good-password");
		fireEvent.click(screen.getByRole("button", { name: "ساخت حساب" }));
		await waitFor(() => expect(done).toHaveBeenCalled());
		expect(register).toHaveBeenCalledWith({
			username: "Emad_H",
			password: "a-good-password",
			password_confirm: "a-good-password",
		});
	});

	it("refuses a username that cannot be one", async () => {
		register.mockReset();
		setup();
		fill(/نام کاربری/, "1x");
		fill(/^رمز/, "a-good-password");
		fill(/تکرار رمز/, "a-good-password");
		fireEvent.click(screen.getByRole("button", { name: "ساخت حساب" }));
		expect(await screen.findByText(/نام کاربری باید ۳ تا ۳۲ نویسه/)).toBeInTheDocument();
		expect(register).not.toHaveBeenCalled();
	});
});
