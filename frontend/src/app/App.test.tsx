import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App placeholder", () => {
  it("has exactly one h1 and a skip link to main", () => {
    render(<App />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const skip = screen.getByRole("link", { name: "Skip to content" });
    expect(skip).toHaveAttribute("href", "#main");
    expect(document.getElementById("main")).toBeInTheDocument();
  });

  it("names the brand for assistive technology", () => {
    render(<App />);
    expect(screen.getByLabelText("DevSync")).toBeInTheDocument();
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(<App />);
    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    const serious = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(serious).toEqual([]);
  });
});
