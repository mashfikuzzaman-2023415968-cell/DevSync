import { createHash } from "node:crypto";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import RegisterPage from "./RegisterPage";

const routes = [
  { path: "/register", element: <RegisterPage /> },
  { path: "/verify", element: <Probe label="verify page" /> },
];

describe("RegisterPage", () => {
  it("starts on role choice and preselects from the URL", async () => {
    renderRoutes(routes, "/register");
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    await userEvent.setup().click(screen.getByLabelText(/I want to hire a team/));
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
  });

  it("skips to details for ?role=developer and shows server field errors", async () => {
    server.use(
      http.get("*/api/v1/auth/csrf", () => {
        document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("*/api/v1/captcha/challenge", () =>
        HttpResponse.json({
          algorithm: "SHA-256",
          challenge: createHash("sha256").update("salt2").digest("hex"),
          max_number: 3,
          salt: "salt",
          signature: "g",
        }),
      ),
      http.post("*/api/v1/auth/register", () =>
        HttpResponse.json(
          {
            error: {
              code: "PASSWORD_REJECTED",
              message: "Choose a stronger password.",
              fields: { password: "This password appears in lists of leaked passwords." },
            },
          },
          { status: 422 },
        ),
      ),
    );
    renderRoutes(routes, "/register?role=developer");
    expect(screen.getByRole("heading", { name: "Your details" })).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Full name"), "Nadia Rahman");
    await user.type(screen.getByLabelText("Email"), "nadia@example.com");
    await user.type(screen.getByLabelText("Mobile number"), "1712345678");
    await user.type(screen.getByLabelText("Password"), "password1234");
    await user.click(screen.getByLabelText(/I agree to the terms/));
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This password appears in lists of leaked passwords.",
    );
  });

  it("solves the check again when the follow-up sign-in asks for it", async () => {
    const logins: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/auth/csrf", () => {
        document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("*/api/v1/captcha/challenge", () =>
        HttpResponse.json({
          algorithm: "SHA-256",
          challenge: createHash("sha256").update("salt2").digest("hex"),
          max_number: 3,
          salt: "salt",
          signature: "g",
        }),
      ),
      http.post("*/api/v1/auth/register", () => HttpResponse.json({ ok: true }, { status: 202 })),
      http.post("*/api/v1/auth/login", async ({ request }) => {
        const body = (await request.json()) as { captcha: string | null };
        logins.push(body.captcha);
        if (!body.captcha) {
          return HttpResponse.json(
            {
              error: {
                code: "CAPTCHA_FAILED",
                message: "Please complete the verification check again.",
                captcha_required: true,
              },
            },
            { status: 403 },
          );
        }
        return HttpResponse.json({ status: "OK", redirect_to: "/verify" });
      }),
    );
    renderRoutes(routes, "/register?role=developer");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Full name"), "Nadia Rahman");
    await user.type(screen.getByLabelText("Email"), "nadia@example.com");
    await user.type(screen.getByLabelText("Mobile number"), "1712345678");
    await user.type(screen.getByLabelText("Password"), "a long passphrase 42");
    await user.click(screen.getByLabelText(/I agree to the terms/));
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("verify page")).toBeInTheDocument();
    expect(logins).toHaveLength(2);
    expect(logins[0]).toBeNull();
    expect(logins[1]).toBeTruthy();
  });

  it("does not retry the sign-in for other errors", async () => {
    let logins = 0;
    server.use(
      http.get("*/api/v1/auth/csrf", () => {
        document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("*/api/v1/captcha/challenge", () =>
        HttpResponse.json({
          algorithm: "SHA-256",
          challenge: createHash("sha256").update("salt2").digest("hex"),
          max_number: 3,
          salt: "salt",
          signature: "g",
        }),
      ),
      http.post("*/api/v1/auth/register", () => HttpResponse.json({ ok: true }, { status: 202 })),
      http.post("*/api/v1/auth/login", () => {
        logins += 1;
        return HttpResponse.json(
          { error: { code: "INVALID_CREDENTIALS", message: "Email or password is incorrect." } },
          { status: 401 },
        );
      }),
    );
    renderRoutes(routes, "/register?role=developer");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Full name"), "Nadia Rahman");
    await user.type(screen.getByLabelText("Email"), "nadia@example.com");
    await user.type(screen.getByLabelText("Mobile number"), "1712345678");
    await user.type(screen.getByLabelText("Password"), "a long passphrase 42");
    await user.click(screen.getByLabelText(/I agree to the terms/));
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(logins).toBe(1);
  });
});
