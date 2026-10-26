/** Code spans in question text (seeded bank uses backticks). */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { inlineCode } from "./inlineCode";

describe("inlineCode", () => {
  it("renders a backticked span as code and drops the backticks", () => {
    render(<p>{inlineCode("Changing the `.current` value of a ref will…")}</p>);
    expect(screen.getByText(".current").tagName).toBe("CODE");
    expect(screen.getByText(/Changing the/).textContent).toBe(
      "Changing the .current value of a ref will…",
    );
  });

  it("handles several spans in one question", () => {
    render(<p>{inlineCode("`useEffect(fn, [])` runs after `null` renders")}</p>);
    expect(screen.getAllByText((_, el) => el?.tagName === "CODE")).toHaveLength(2);
  });

  it("leaves text without backticks exactly as written", () => {
    expect(inlineCode("What does a component return?")).toBe("What does a component return?");
  });

  it("keeps an unclosed backtick as written rather than swallowing the rest", () => {
    render(<p>{inlineCode("a `b` and a stray ` here")}</p>);
    expect(screen.getByText(/stray/).textContent).toBe("a b and a stray ` here");
  });

  it("never treats the text as markup", () => {
    const { container } = render(<p>{inlineCode("`<img src=x onerror=alert(1)>`")}</p>);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>").tagName).toBe("CODE");
  });
});
