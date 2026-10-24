/** Public project list and project page (spec §13.5 #6; audit round 2). */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import PublicProjectPage from "./PublicProjectPage";
import PublicProjectsPage from "./PublicProjectsPage";

const API = "*/api/v1";
const CARD = {
  id: "p1",
  title: "Online ordering system",
  summary: "Customers order online; staff track orders.",
  skills: ["React", "FastAPI"],
  budget_paisa: 12_000_000,
  deadline_days: 30,
  team_size: 4,
  status: "BIDDING",
  open_for_bids: true,
  bidding_deadline: "2026-11-05T06:00:00Z",
  created_at: "2026-10-20T06:00:00Z",
};
const DETAIL = {
  ...CARD,
  requirements: "React front end, FastAPI back end.",
  slots: [{ id: "s1", skill_id: "k1", skill: "React", label: "", count: 2 }],
};

function signedOut() {
  return http.get(`${API}/me`, () =>
    HttpResponse.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 }),
  );
}

describe("PublicProjectsPage", () => {
  it("lists the open projects from the server, each linking to its page", async () => {
    server.use(
      signedOut(),
      http.get(`${API}/public/projects`, () =>
        HttpResponse.json({ items: [CARD], next_cursor: null }),
      ),
    );
    renderRoutes([{ path: "/projects", element: <PublicProjectsPage /> }], "/projects");
    const link = await screen.findByRole("link", { name: "Online ordering system" });
    expect(link).toHaveAttribute("href", "/p/p1");
    expect(screen.getByText("৳1,20,000")).toBeInTheDocument();
    expect(screen.queryByText(/No projects are open/)).not.toBeInTheDocument();
  });

  it("searches, keeps the words in the address and loads more", async () => {
    const user = userEvent.setup();
    const asked: string[] = [];
    server.use(
      signedOut(),
      http.get(`${API}/public/projects`, ({ request }) => {
        const url = new URL(request.url);
        asked.push(url.search);
        if (url.searchParams.get("cursor") === "c2") {
          return HttpResponse.json({
            items: [{ ...CARD, id: "p2", title: "Mobile app" }],
            next_cursor: null,
          });
        }
        return HttpResponse.json({ items: [CARD], next_cursor: "c2" });
      }),
    );
    const { router } = renderRoutes(
      [{ path: "/projects", element: <PublicProjectsPage /> }],
      "/projects",
    );
    await user.type(await screen.findByLabelText("Search projects"), "react");
    await user.click(screen.getByRole("button", { name: /Search/ }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("?q=react");
    });
    await user.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("link", { name: "Mobile app" })).toBeInTheDocument();
    expect(asked).toContain("?q=react&cursor=c2");
  });

  it("says when nothing matches and offers to clear the search", async () => {
    server.use(
      signedOut(),
      http.get(`${API}/public/projects`, () => HttpResponse.json({ items: [], next_cursor: null })),
    );
    renderRoutes([{ path: "/projects", element: <PublicProjectsPage /> }], "/projects?q=cobol");
    expect(await screen.findByText("No open projects match “cobol”")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear the search" })).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    server.use(
      signedOut(),
      http.get(`${API}/public/projects`, () =>
        HttpResponse.json({ error: { code: "INTERNAL_ERROR" } }, { status: 500 }),
      ),
    );
    renderRoutes([{ path: "/projects", element: <PublicProjectsPage /> }], "/projects");
    expect(await screen.findByText("We couldn’t load the projects")).toBeInTheDocument();
  });
});

describe("PublicProjectPage", () => {
  const routes = [
    { path: "/p/:id", element: <PublicProjectPage /> },
    { path: "*", element: <Probe label="elsewhere" /> },
  ];

  it("shows the project and a sign-in that returns to the bid sheet", async () => {
    server.use(
      signedOut(),
      http.get(`${API}/public/projects/p1`, () => HttpResponse.json(DETAIL)),
    );
    renderRoutes(routes, "/p/p1");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Online ordering system" }),
    ).toBeInTheDocument();
    expect(screen.getByText("React front end, FastAPI back end.")).toBeInTheDocument();
    expect(screen.getByText("React ×2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in to bid" })).toHaveAttribute(
      "href",
      "/login?return_to=%2Fdev%2Fprojects%2Fp1",
    );
  });

  it("sends a signed-in developer straight to the bid sheet", async () => {
    server.use(
      http.get(`${API}/me`, () => HttpResponse.json({ id: "u1", role: "DEVELOPER" })),
      http.get(`${API}/public/projects/p1`, () => HttpResponse.json(DETAIL)),
    );
    renderRoutes(routes, "/p/p1");
    expect(await screen.findByRole("link", { name: "Place a sealed bid" })).toHaveAttribute(
      "href",
      "/dev/projects/p1",
    );
  });

  it("says when bidding has closed", async () => {
    server.use(
      signedOut(),
      http.get(`${API}/public/projects/p1`, () =>
        HttpResponse.json({ ...DETAIL, open_for_bids: false }),
      ),
    );
    renderRoutes(routes, "/p/p1");
    expect(await screen.findByText("Bidding has closed")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Sign in to bid" })).not.toBeInTheDocument();
  });

  it("explains a project that isn't public", async () => {
    server.use(
      signedOut(),
      http.get(`${API}/public/projects/p1`, () =>
        HttpResponse.json({ error: { code: "NOT_FOUND" } }, { status: 404 }),
      ),
    );
    renderRoutes(routes, "/p/p1");
    expect(await screen.findByText("This project isn’t open to view")).toBeInTheDocument();
  });
});
