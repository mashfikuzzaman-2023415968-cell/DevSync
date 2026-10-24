/** The reputation summary on the public developer profile (spec §13.5 #7, D48, D55). */
import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { renderRoutes } from "@/test/render";
import PublicProfilePage from "./PublicProfilePage";

const PROFILE = {
  id: "dev-1",
  display_name: "Nadia Rahman",
  member_since: "2026-10-01T00:00:00Z",
  headline: "React developer",
  bio: "",
  hours_per_week: 20,
  github_username: null,
  visibility: "PUBLIC",
  skills: [],
  verified_scores: [],
  portfolio: [],
  certificates: [],
};

const ME = {
  id: "client-1",
  email: "rahim@example.com",
  display_name: "Rahim Uddin",
  role: "CLIENT",
  status: "ACTIVE",
  phone_e164: null,
  phone_verified: true,
  email_verified: true,
  payment_verified: true,
  totp_enabled: false,
  totp_verified: false,
  created_at: "2026-10-01T00:00:00Z",
};

function render(reputation: object | null, signedIn = true) {
  server.use(
    http.get("*/api/v1/auth/csrf", () => new HttpResponse(null, { status: 204 })),
    http.get("*/api/v1/me", () =>
      signedIn
        ? HttpResponse.json(ME)
        : HttpResponse.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 }),
    ),
    http.get("*/api/v1/developers/dev-1", () => HttpResponse.json({ ...PROFILE, reputation })),
    http.get("*/api/v1/public/developers/dev-1", () =>
      HttpResponse.json({ ...PROFILE, reputation }),
    ),
  );
  renderRoutes([{ path: "/d/:id", element: <PublicProfilePage /> }], "/d/dev-1");
}

async function reputationCard(): Promise<HTMLElement> {
  const heading = await screen.findByRole("heading", { level: 2, name: "Reputation" });
  const card = heading.closest("div.rounded-lg");
  if (!(card instanceof HTMLElement)) throw new Error("no reputation card");
  return card;
}

describe("PublicProfilePage reputation", () => {
  it("shows C and P on 0–100", async () => {
    render({ competency: "0.712", performance: "0.768", is_newcomer: false, seeded: false });
    const card = await reputationCard();
    expect(within(card).getByText("Competency").nextSibling).toHaveTextContent("71");
    expect(within(card).getByText("Performance").nextSibling).toHaveTextContent("77");
    expect(within(card).queryByText("Newcomer")).not.toBeInTheDocument();
    expect(within(card).queryByText("Seeded for the demo.")).not.toBeInTheDocument();
  });

  it("marks seeded demo values", async () => {
    render({ competency: "0.712", performance: "0.768", is_newcomer: false, seeded: true });
    const card = await reputationCard();
    expect(within(card).getByText("Seeded for the demo.")).toBeInTheDocument();
  });

  it("shows the newcomer badge with values when a newcomer has a snapshot", async () => {
    render({ competency: "0.500", performance: "0.450", is_newcomer: true, seeded: false });
    const card = await reputationCard();
    expect(within(card).getByText("Newcomer")).toBeInTheDocument();
    expect(within(card).getByText("Competency").nextSibling).toHaveTextContent("50");
  });

  it("says a newcomer without a record is building one", async () => {
    render({ competency: null, performance: null, is_newcomer: true, seeded: false });
    const card = await reputationCard();
    expect(within(card).getByText("Building a record")).toBeInTheDocument();
    expect(within(card).getByText("Newcomer")).toBeInTheDocument();
    expect(within(card).queryByText("Competency")).not.toBeInTheDocument();
  });

  it("invites anonymous visitors to sign in instead of showing scores", async () => {
    render(null, false);
    const card = await reputationCard();
    expect(within(card).getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "/login?return_to=%2Fd%2Fdev-1",
    );
    expect(within(card).queryByText("Competency")).not.toBeInTheDocument();
    expect(within(card).queryByText("Building a record")).not.toBeInTheDocument();
  });
});
