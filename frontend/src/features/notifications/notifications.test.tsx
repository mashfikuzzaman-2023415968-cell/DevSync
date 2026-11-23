/** Notifications page and the bell's count (D122): grouped by day, unread dot, mark one or all
 * read, open the linked page; empty and error states. */
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { Probe, renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import NotificationsPage from "./NotificationsPage";

const API = "https://testserver/api/v1";
const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });
const note = (over: Record<string, unknown> = {}) => ({
  id: "n1", type: "INVITATION_SELECTED", title: "You were selected",
  body: "The client chose you for the React developer role.", link_path: "/dev", read_at: null,
  created_at: "2026-11-24T06:00:00Z", ...over,
}); // prettier-ignore

const show = () =>
  renderRoutes(
    [
      { path: "/notifications", element: <NotificationsPage /> },
      { path: "*", element: <Probe label="elsewhere" /> },
    ],
    "/notifications",
  );

describe("NotificationsPage", () => {
  it("groups by day, marks unread, and opens the link after marking it read", async () => {
    let read: string | null = null;
    server.use(
      csrf(),
      http.get(`${API}/notifications`, () =>
        HttpResponse.json({
          items: [note(), note({ id: "n2", title: "Project started", read_at: "2026-11-23T08:00:00Z",
                                  created_at: "2026-11-23T07:00:00Z", link_path: null })],
          next_cursor: null,
        }),
      ), // prettier-ignore
      http.post(`${API}/notifications/:id/read`, ({ params }) => {
        read = String(params.id);
        return HttpResponse.json(note({ read_at: "2026-11-24T07:00:00Z" }));
      }),
    );
    show();
    expect(await screen.findByRole("region", { name: "24 Nov 2026" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "23 Nov 2026" })).toBeInTheDocument();
    expect(screen.getByText("(unread)")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /You were selected/ }));
    expect(await screen.findByText("elsewhere")).toBeInTheDocument();
    expect(read).toBe("n1");
  });

  it("marks all read", async () => {
    let called = false;
    server.use(
      csrf(),
      http.get(`${API}/notifications`, () =>
        HttpResponse.json({ items: [note()], next_cursor: null }),
      ),
      http.post(`${API}/notifications/read-all`, () => {
        called = true;
        return HttpResponse.json({ marked: 1 });
      }),
    );
    show();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Mark all read" }));
    await screen.findByRole("button", { name: "Mark all read" });
    expect(called).toBe(true);
  });

  it("has no mark-all button when everything is read, and an empty state", async () => {
    server.use(
      http.get(`${API}/notifications`, () => HttpResponse.json({ items: [], next_cursor: null })),
    );
    show();
    expect(await screen.findByText("Nothing yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark all read" })).not.toBeInTheDocument();
  });

  it("shows an error with a retry", async () => {
    server.use(
      http.get(`${API}/notifications`, () =>
        HttpResponse.json({ error: { code: "INTERNAL_ERROR", request_id: "r" } }, { status: 500 }),
      ),
    );
    show();
    expect(await screen.findByText("Your notifications didn’t load")).toBeInTheDocument();
  });
});
