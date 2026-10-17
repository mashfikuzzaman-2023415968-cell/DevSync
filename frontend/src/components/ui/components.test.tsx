import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Alert } from "./Feedback";
import { Button } from "./Button";
import { Field } from "./Field";
import { OtpInput } from "./OtpInput";
import { PasswordMeter, strength } from "./PasswordMeter";

function Otp({ onDone }: { onDone?: (v: string) => void }) {
  const [v, setV] = useState("");
  return (
    <OtpInput
      label="Code"
      value={v}
      onChange={(next) => {
        setV(next);
        onDone?.(next);
      }}
      focusFirst
    />
  );
}

describe("OtpInput", () => {
  it("auto-advances, accepts digits only and supports backspace", async () => {
    const user = userEvent.setup();
    render(<Otp />);
    const boxes = screen.getAllByRole("textbox");
    expect(boxes).toHaveLength(6);
    expect(boxes[0]).toHaveFocus();
    await user.keyboard("1a2");
    expect(boxes[0]).toHaveValue("1");
    expect(boxes[1]).toHaveValue("2");
    expect(boxes[2]).toHaveFocus();
    await user.keyboard("{Backspace}");
    expect(boxes[1]).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(boxes[0]).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(boxes[1]).toHaveFocus();
  });

  it("fills all boxes from a paste", () => {
    const done = vi.fn();
    render(<Otp onDone={done} />);
    const first = screen.getAllByRole("textbox")[0] as HTMLInputElement;
    fireEvent.paste(first, { clipboardData: { getData: () => "12 34-56 78" } });
    expect(done).toHaveBeenLastCalledWith("123456");
  });
});

describe("PasswordMeter", () => {
  it.each([
    ["", 0],
    ["aaaaaaaaaaaaaaaaaa", 0],
    ["short", 0],
    ["longenough", 1],
    ["correcthorsebat", 2],
    ["correct horse battery", 4],
    ["correct horse battery 42", 4],
  ])("strength(%s) = %i", (pw, score) => {
    expect(strength(pw)).toBe(score);
  });

  it("announces the label", () => {
    render(<PasswordMeter password="correct horse battery 42" />);
    expect(screen.getByText("Looks strong.")).toBeInTheDocument();
    expect(screen.getByText(/we check it against leaked/)).toBeInTheDocument();
  });
});

describe("Field, Button, Alert", () => {
  it("links label, hint and error for assistive technology", () => {
    const { rerender } = render(<Field label="Email" hint="Work email is fine" />);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAccessibleDescription("Work email is fine");
    rerender(<Field label="Email" error="Enter a valid email address." />);
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid email address.");
  });

  it("disables while loading", () => {
    render(<Button loading>Sign in</Button>);
    const button = screen.getByRole("button", { name: "Sign in" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("states tone in text, not colour alone, and has no serious axe issues", async () => {
    const { container } = render(
      <>
        <Alert tone="danger">Email or password is incorrect.</Alert>
        <Alert tone="success">Saved.</Alert>
      </>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Error:");
    expect(screen.getByRole("status")).toHaveTextContent("Done:");
    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(
      results.violations.filter((v) => v.impact === "serious" || v.impact === "critical"),
    ).toEqual([]);
  });
});
