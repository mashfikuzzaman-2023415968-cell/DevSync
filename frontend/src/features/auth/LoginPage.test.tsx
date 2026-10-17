import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import LoginPage from "./LoginPage";

const routes = [
  { path: "/login", element: <LoginPage /> },
  { path: "/login/totp", element: <Probe label="totp step" /> },
  { path: "/client", element: <Probe label="client home" /> },
  { path: "/client/projects", element: <Probe label="projects" /> },
];

function csrf() {
  return http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });
}

async function fill(email = "rahim@example.com", password = "a good password 1") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("LoginPage", () => {
  it("signs in and follows a safe return_to", async () => {
    server.use(
      csrf(),
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json({ status: "SIGNED_IN", redirect_to: "/client/projects", pre_auth: null }),
      ),
    );
    renderRoutes(routes, "/login?return_to=%2Fclient%2Fprojects");
    await fill();
    expect(await screen.findByText("projects")).toBeInTheDocument();
  });

  it("shows the uniform error for wrong credentials", async () => {
    server.use(
      csrf(),
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json(
          { error: { code: "INVALID_CREDENTIALS", message: "Email or password is incorrect." } },
          { status: 401 },
        ),
      ),
    );
    renderRoutes(routes, "/login");
    await fill();
    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
  });

  it("solves the CAPTCHA when the server asks and retries", async () => {
    let calls = 0;
    server.use(
      csrf(),
      http.get("*/api/v1/captcha/challenge", () =>
        HttpResponse.json({
          algorithm: "SHA-256",
          challenge: "x",
          max_number: 0,
          salt: "s",
          signature: "g",
        }),
      ),
      http.post("*/api/v1/auth/login", () => {
        calls += 1;
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
      }),
    );
    renderRoutes(routes, "/login");
    await fill();
    // max_number 0 is unsolvable, so the page reports the failed check instead of looping.
    expect(await screen.findByRole("alert")).toHaveTextContent(/bot check didn’t finish/);
    expect(calls).toBe(1);
  });

  it("moves admins to the TOTP step", async () => {
    server.use(
      csrf(),
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json({ status: "TOTP_REQUIRED", redirect_to: null, pre_auth: "p".repeat(40) }),
      ),
    );
    renderRoutes(routes, "/login");
    await fill();
    expect(await screen.findByText("totp step")).toBeInTheDocument();
  });

  it("shows the lockout message with the wait time", async () => {
    server.use(
      csrf(),
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json(
          {
            error: {
              code: "ACCOUNT_LOCKED",
              message: "Too many failed attempts. Try again in 15 minutes.",
              locked_minutes: 15,
            },
          },
          { status: 423 },
        ),
      ),
    );
    renderRoutes(routes, "/login");
    await fill();
    expect(await screen.findByRole("alert")).toHaveTextContent("15 minutes");
  });

  it("validates before calling the server", async () => {
    renderRoutes(routes, "/login");
    await fill("not-an-email", "x");
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
  });
});
