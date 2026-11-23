/** Workspace Team tab (screen 33; D120, D130): members without anyone's price, the Phase 9 tabs
 * marked, leaving with a reason of the right length, asking for a lead change; 404 for others. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { Toaster } from "@/components/ui/Toaster";
import { renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import WorkspaceTeamPage from "./WorkspaceTeamPage";

const API = "https://testserver/api/v1";
const PID = "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c";
const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });
const member = (over: Record<string, unknown> = {}) => ({
  id: "m1", developer_id: "d1", developer_name: "Nusrat Jahan", slot_id: "s1",
  slot_label: "React developer", status: "ACTIVE", is_lead: true, is_newcomer: false,
  competency: 0.74, teamwork: 0.66, hours_per_week: 20, joined_at: null, invitation: null,
  is_you: false, ...over,
}); // prettier-ignore
const view = {
  project_id: PID, project_title: "Online ordering system", project_status: "IN_PROGRESS",
  project_version: 6, team_id: "t", team_status: "ACTIVE", lead_member_id: "m1", view: "member",
  members: [member(), member({ id: "m2", developer_id: "d2", developer_name: "Arif Hasan",
                               is_lead: false, is_you: true })],
  my_member_id: "m2", lead_change_requests: [],
}; // prettier-ignore

const show = () =>
  renderRoutes(
    [
      {
        path: "/w/:projectId/team",
        element: (
          <>
            <WorkspaceTeamPage />
            <Toaster />
          </>
        ),
      },
    ],
    `/w/${PID}/team`,
  );

describe("WorkspaceTeamPage", () => {
  it("lists members without prices and marks the Phase 9 tabs", async () => {
    server.use(http.get(`${API}/projects/${PID}/team`, () => HttpResponse.json(view)));
    show();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Online ordering system" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Lead")).toBeInTheDocument();
    expect(screen.getByText("(you)")).toBeInTheDocument();
    expect(screen.queryByText(/৳/)).not.toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Workspace" });
    expect(within(nav).getByText("Team")).toHaveAttribute("aria-current", "page");
    expect(within(nav).getAllByText("(arrives in Phase 9)")).toHaveLength(8);
  });

  it("leaves only with a reason of 20–500 characters", async () => {
    let body: unknown = null;
    server.use(
      csrf(),
      http.get(`${API}/projects/${PID}/team`, () => HttpResponse.json(view)),
      http.post(`${API}/team-members/m2/leave`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ status: "LEFT", message: "ok" });
      }),
    );
    show();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Leave project" }));
    const dialog = await screen.findByRole("dialog", { name: "Leave this project?" });
    const box = within(dialog).getByRole("textbox");
    const leave = within(dialog).getByRole("button", { name: "Leave project" });
    await user.type(box, "x".repeat(19));
    expect(leave).toBeDisabled();
    await user.type(box, "x");
    expect(leave).toBeEnabled();
    await user.click(leave);
    expect(await screen.findByText("You left the project")).toBeInTheDocument();
    expect(body).toEqual({ reason: "x".repeat(20) });
  });

  it("asks for a lead change", async () => {
    let body: unknown = null;
    server.use(
      csrf(),
      http.get(`${API}/projects/${PID}/team`, () => HttpResponse.json(view)),
      http.post(`${API}/projects/${PID}/lead-change-requests`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    show();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Ask for a lead change" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox"), "The lead hasn't answered for a week.");
    await user.click(within(dialog).getByRole("button", { name: "Send request" }));
    expect(await screen.findByText("Request sent")).toBeInTheDocument();
    expect(body).toEqual({ reason: "The lead hasn't answered for a week." });
  });

  it("says not found for anyone outside the team", async () => {
    server.use(
      http.get(`${API}/projects/${PID}/team`, () =>
        HttpResponse.json({ error: { code: "NOT_FOUND", request_id: "r" } }, { status: 404 }),
      ),
    );
    show();
    expect(await screen.findByText("We couldn’t find that workspace")).toBeInTheDocument();
  });
});
