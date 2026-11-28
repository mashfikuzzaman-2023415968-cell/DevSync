/** Discussion tab (D146): threads most recently active first, opening one from the list or the
 * address (`?thread=`), its posts through the thread endpoints, replying, starting a thread with
 * its bounds, the empty, unknown-thread, error and read-only states; the thread form schema. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { CommentItem, Thread } from "@/api/types";
import { Toaster } from "@/components/ui/Toaster";
import { renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import DiscussionTab, { threadSchema } from "./DiscussionTab";
import WorkspaceLayout from "./WorkspaceLayout";

const API = "https://testserver/api/v1";
const PID = "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c";
const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });
const member = {
  id: "m2", developer_id: "dev", developer_name: "Nusrat Jahan", slot_id: "s1",
  slot_label: "React developer", status: "ACTIVE", is_lead: false, is_newcomer: false,
  competency: 0.7, teamwork: 0.6, hours_per_week: 20, joined_at: null, invitation: null,
  is_you: true,
}; // prettier-ignore
const team = (status = "IN_PROGRESS") => ({
  project_id: PID, project_title: "Inventory dashboard", project_status: status,
  project_version: 3, team_id: "t", team_status: "ACTIVE", lead_member_id: "m1", view: "member",
  members: [member], my_member_id: "m2", lead_change_requests: [],
}); // prettier-ignore
const thread = (id: string, title: string, over: Partial<Thread> = {}): Thread => ({
  id, title, created_by: { id: "dev", name: "Nusrat Jahan" }, created_at: "2026-12-14T05:00:00Z",
  last_post_at: "2026-12-14T06:00:00Z", post_count: 2, ...over,
}); // prettier-ignore
const post = (id: string, threadId: string, body: string): CommentItem => ({
  id, target_type: "DISCUSSION_POST", target_id: threadId, author: { id: "dev", name: "Nusrat Jahan" },
  body, mentions: [], reply_to_id: null, created_at: "2026-12-14T05:00:00Z", edited: false,
  deleted: false, can_edit: false, version: 1,
}); // prettier-ignore
const me = { id: "dev", email: "n@example.com", role: "DEVELOPER", display_name: "Nusrat Jahan" };

function show(threads: Thread[], path = `/w/${PID}/discussion`, status = "IN_PROGRESS") {
  server.use(
    csrf(),
    http.get(`${API}/me`, () => HttpResponse.json(me)),
    http.get(`${API}/projects/${PID}/team`, () => HttpResponse.json(team(status))),
    http.get(`${API}/projects/${PID}/threads`, () =>
      HttpResponse.json({ items: threads, next_cursor: null }),
    ),
    http.get(`${API}/threads/:id/posts`, ({ params }) =>
      HttpResponse.json({
        items: [post("p1", String(params.id), `Opening post of ${String(params.id)}`)],
        next_cursor: null,
      }),
    ),
  );
  renderRoutes(
    [
      {
        path: "/w/:projectId",
        element: (
          <>
            <WorkspaceLayout />
            <Toaster />
          </>
        ),
        children: [{ path: "discussion", element: <DiscussionTab /> }],
      },
    ],
    path,
  );
}

describe("DiscussionTab", () => {
  it("lists threads and opens one with its posts", async () => {
    show([thread("t1", "Release checklist"), thread("t2", "API naming", { post_count: 1 })]);
    const list = await screen.findByRole("region", { name: "Threads" });
    const buttons = within(list).getAllByRole("button", { name: /posts?, last/ });
    expect(buttons.map((b) => b.textContent)).toEqual([
      expect.stringContaining("Release checklist"),
      expect.stringContaining("API naming"),
    ]);
    expect(within(list).getByText(/1 post, last/)).toBeInTheDocument();
    expect(screen.getByText("Choose a thread")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(within(list).getByRole("button", { name: /API naming/ }));
    expect(await screen.findByText("Opening post of t2")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "API naming" })).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: /API naming/ })).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("opens the thread named in the address and replies through the thread endpoint", async () => {
    let sent: unknown = null;
    const posts = [post("p1", "t1", "Opening post of t1")];
    show([thread("t1", "Release checklist")], `/w/${PID}/discussion?thread=t1`);
    server.use(
      http.get(`${API}/threads/t1/posts`, () =>
        HttpResponse.json({ items: posts, next_cursor: null }),
      ),
      http.post(`${API}/threads/t1/posts`, async ({ request }) => {
        sent = await request.json();
        posts.push(post("p2", "t1", "Agreed"));
        return HttpResponse.json(posts[1], { status: 201 });
      }),
    );
    expect(await screen.findByText("Opening post of t1")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "Write a post" }), "Agreed");
    await user.click(screen.getByRole("button", { name: "Post" }));
    expect(await screen.findByText("Agreed")).toBeInTheDocument();
    expect(sent).toEqual({ body: "Agreed", mention_ids: [], reply_to_id: null });
  });

  it("starts a thread after checking the title and first post", async () => {
    let sent: unknown = null;
    show([]);
    server.use(
      http.post(`${API}/projects/${PID}/threads`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json(thread("t9", "Demo plan", { post_count: 1 }), { status: 201 });
      }),
    );
    expect(await screen.findByText("No threads yet")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "New thread" }));
    await user.type(screen.getByLabelText("Title"), "Hi");
    await user.click(screen.getByRole("button", { name: "Start thread" }));
    expect(
      await screen.findByText("Give the thread a title of at least 3 characters"),
    ).toBeInTheDocument();
    expect(screen.getByText("Write the first post")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "Demo plan");
    await user.type(screen.getByLabelText(/First post/), "Who presents what?");
    await user.click(screen.getByRole("button", { name: "Start thread" }));
    expect(await screen.findByText("Thread started")).toBeInTheDocument();
    expect(sent).toEqual({ title: "Demo plan", body: "Who presents what?", mention_ids: [] });
  });

  it("says when the linked thread isn't in the list", async () => {
    show([thread("t1", "Release checklist")], `/w/${PID}/discussion?thread=missing`);
    expect(await screen.findByText("This thread isn’t here")).toBeInTheDocument();
  });

  it("is read-only once the project is finished", async () => {
    show([thread("t1", "Release checklist")], `/w/${PID}/discussion?thread=t1`, "COMPLETED");
    expect(await screen.findByText("Opening post of t1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New thread" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Write a post" })).not.toBeInTheDocument();
  });

  it("explains a failed load", async () => {
    show([]);
    server.use(
      http.get(`${API}/projects/${PID}/threads`, () =>
        HttpResponse.json({ error: { code: "INTERNAL_ERROR", message: "x" } }, { status: 500 }),
      ),
    );
    expect(await screen.findByText("The discussion didn’t load")).toBeInTheDocument();
  });
});

describe("threadSchema", () => {
  it("bounds the title and the first post", () => {
    const ok = { title: "abc", body: "x" };
    expect(threadSchema.safeParse(ok).success).toBe(true);
    expect(threadSchema.safeParse({ ...ok, title: "ab" }).success).toBe(false);
    expect(threadSchema.safeParse({ ...ok, title: "t".repeat(120) }).success).toBe(true);
    expect(threadSchema.safeParse({ ...ok, title: "t".repeat(121) }).success).toBe(false);
    expect(threadSchema.safeParse({ ...ok, body: "   " }).success).toBe(false);
    expect(threadSchema.safeParse({ ...ok, body: "x".repeat(4001) }).success).toBe(false);
  });
});
