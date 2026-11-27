/** The comment linkifier (§13.7, D146): only https URLs become links; other schemes, credentials
 * and trailing punctuation stay text; markup is never interpreted. */
import { describe, expect, it } from "vitest";
import { linkify } from "./linkify";

const links = (text: string) => linkify(text).filter((s) => s.kind === "link").map((s) => s.value);

describe("linkify", () => {
  it("links https URLs and keeps the rest as text", () => {
    expect(linkify("See https://github.com/acme/inv/pull/12 please")).toEqual([
      { kind: "text", value: "See " },
      {
        kind: "link",
        value: "https://github.com/acme/inv/pull/12",
        href: "https://github.com/acme/inv/pull/12",
      },
      { kind: "text", value: " please" },
    ]);
  });

  it.each([
    "javascript:alert(1)",
    "JAVASCRIPT:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "http://example.com",
    "HTTPS://EXAMPLE.COM",
    "ftp://example.com",
    "https://user:pass@example.com",
    "https://",
    "vbscript:msgbox(1)",
  ])("never links %s", (text) => {
    expect(links(text)).toEqual([]);
    expect(linkify(text).map((s) => s.value).join("")).toBe(text);
  });

  it("leaves sentence punctuation outside the link", () => {
    expect(links("Done (https://example.com/a).")).toEqual(["https://example.com/a"]);
    expect(links("https://example.com/b, https://example.com/c!")).toEqual([
      "https://example.com/b",
      "https://example.com/c",
    ]);
  });

  it("stops a URL at markup characters", () => {
    expect(links('https://example.com/"><img src=x onerror=alert(1)>')).toEqual([
      "https://example.com/",
    ]);
  });

  it("keeps all of the text, in order", () => {
    const text = "a https://x.org b <script>c</script>";
    expect(linkify(text).map((s) => s.value).join("")).toBe(text);
  });

  it("refuses absurdly long URLs", () => {
    expect(links(`https://example.com/${"a".repeat(2100)}`)).toEqual([]);
  });
});
