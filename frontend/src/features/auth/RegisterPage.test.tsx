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
    expect(await screen.findByText(/leaked passwords/)).toBeInTheDocument();
  });
});
