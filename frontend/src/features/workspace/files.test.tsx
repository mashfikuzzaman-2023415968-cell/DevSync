/** Files tab (screen 35; D147): the list with uploader, size and evidence links, download links
 * through the API, uploading with the local type/size checks and the server's answer, deleting
 * only where allowed (with confirmation), the empty, error and read-only states; plus the file
 * evidence rules of the task drawer's form and the size formatter. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { ProjectFile } from "@/api/types";
import { Toaster } from "@/components/ui/Toaster";
import { formatBytes } from "@/lib/format";
import { renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import FilesTab from "./FilesTab";
import { sizeProblem } from "./filesApi";
import { evidenceFormSchema } from "./schemas";
import WorkspaceLayout from "./WorkspaceLayout";

const API = "https://testserver/api/v1";
const PID = "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c";
const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });
const member = {
  id: "m2", developer_id: "dev", developer_name: "Farhan Hossain", slot_id: "s1",
  slot_label: "Backend developer", status: "ACTIVE", is_lead: false, is_newcomer: false,
  competency: 0.7, teamwork: 0.6, hours_per_week: 20, joined_at: null, invitation: null,
  is_you: true,
}; // prettier-ignore
const team = (view: "member" | "client", status = "IN_PROGRESS") => ({
  project_id: PID, project_title: "Inventory dashboard", project_status: status,
  project_version: 3, team_id: "t", team_status: "ACTIVE", lead_member_id: "m1", view,
  members: [member], my_member_id: "m2", lead_change_requests: [],
  ...(view === "client" ? { recommendation: null, can_choose_lead: false, can_start: false,
                            start_blockers: [], removal_requests: [], repair: null } : {}),
}); // prettier-ignore
const file = (id: string, over: Partial<ProjectFile> = {}): ProjectFile => ({
  id, name: `${id}.pdf`, mime: "application/pdf", size_bytes: 204800,
  uploaded_by: { id: "dev", name: "Farhan Hossain" }, created_at: "2026-12-14T05:30:00Z",
  can_delete: false, links: [], ...over,
}); // prettier-ignore

function show(files: ProjectFile[], view: "member" | "client" = "member", status = "IN_PROGRESS") {
  server.use(
    csrf(),
    http.get(`${API}/projects/${PID}/team`, () => HttpResponse.json(team(view, status))),
    http.get(`${API}/projects/${PID}/files`, () =>
      HttpResponse.json({ items: files, next_cursor: null }),
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
        children: [{ path: "files", element: <FilesTab /> }],
      },
    ],
    `/w/${PID}/files`,
  );
}

const png = () => new File([new Uint8Array([137, 80, 78, 71, 1, 2, 3])], "board.png", { type: "image/png" });

describe("FilesTab", () => {
  it("lists files with who, when, how big and the tasks that use them", async () => {
    show([
      file("wireframes", {
        links: [{ task_id: "t1", task_title: "UI kit", milestone_title: "UI design" }],
      }),
      file("notes", { name: "notes.md", mime: "text/plain", size_bytes: 820 }),
    ]);
    const row = (await screen.findByText("wireframes.pdf")).closest("li");
    if (!row) throw new Error("row missing");
    expect(within(row).getByText(/Farhan Hossain, 14 Dec 2026, 200 KB/)).toBeInTheDocument();
    expect(within(row).getByText("UI kit")).toBeInTheDocument();
    expect(within(row).getByText(/UI design/)).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Download wireframes.pdf" })).toHaveAttribute(
      "href",
      expect.stringMatching(/\/api\/v1\/files\/wireframes\/download$/),
    );
    expect(screen.getByText(/820 bytes/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
  });

  it("uploads a file and says so", async () => {
    let calls = 0;
    show([]);
    server.use(
      http.post(`${API}/projects/${PID}/files`, () => {
        calls += 1;
        return HttpResponse.json(file("board", { name: "board.png", mime: "image/png" }), {
          status: 201,
        });
      }),
    );
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText(/Choose a file to upload/), png());
    expect(await screen.findByText("Uploaded board.png")).toBeInTheDocument();
    expect(calls).toBe(1);
  });

  it("refuses wrong types and sizes before sending, and shows the server's refusal", async () => {
    let calls = 0;
    show([]);
    server.use(
      http.post(`${API}/projects/${PID}/files`, () => {
        calls += 1;
        return HttpResponse.json(
          { error: { code: "PAYLOAD_TOO_LARGE", message: "This type of file can be at most 10 MB." } },
          { status: 413 },
        );
      }),
    );
    const user = userEvent.setup({ applyAccept: false });
    const input = await screen.findByLabelText(/Choose a file to upload/);
    await user.upload(input, new File(["PK"], "source.zip", { type: "application/zip" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Choose PDF up to 10 MB/);
    await user.upload(
      input,
      new File([new Uint8Array(1024 * 1024 + 1)], "big.txt", { type: "text/plain" }),
    );
    expect(await screen.findByText("A text or Markdown file can be at most 1 MB.")).toBeInTheDocument();
    expect(calls).toBe(0);
    await user.upload(input, new File(["%PDF-1.7"], "spec.pdf", { type: "application/pdf" }));
    expect(await screen.findByText("This type of file can be at most 10 MB.")).toBeInTheDocument();
    expect(calls).toBe(1);
  });

  it("deletes a file after confirmation, only where allowed", async () => {
    let deleted: string | null = null;
    show([file("mine", { can_delete: true }), file("theirs")]);
    server.use(
      http.delete(`${API}/files/:id`, ({ params }) => {
        deleted = String(params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    expect(await screen.findByText("theirs.pdf")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete theirs.pdf" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete mine.pdf" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/can’t be downloaded any more/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Delete file" }));
    expect(await screen.findByText("File deleted")).toBeInTheDocument();
    expect(deleted).toBe("mine");
  });

  it("shows the empty state; the client may upload too", async () => {
    show([], "client");
    expect(await screen.findByText("No files yet")).toBeInTheDocument();
    expect(screen.getByLabelText(/Choose a file to upload/)).toBeInTheDocument();
  });

  it("is read-only once the project is no longer in progress", async () => {
    show([file("final", { can_delete: false })], "member", "COMPLETED");
    expect(await screen.findByText("final.pdf")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Choose a file to upload/)).not.toBeInTheDocument();
  });

  it("explains a failed load and offers to try again", async () => {
    show([]);
    server.use(
      http.get(`${API}/projects/${PID}/files`, () =>
        HttpResponse.json({ error: { code: "INTERNAL_ERROR", message: "x" } }, { status: 500 }),
      ),
    );
    expect(await screen.findByText("Files didn’t load")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Try again/ })).toBeInTheDocument();
  });
});

describe("file rules", () => {
  it("checks the per-type sizes the server applies", () => {
    const sized = (bytes: number, type: string) => new File([new Uint8Array(bytes)], "f", { type });
    expect(sizeProblem(sized(10 * 1024 * 1024, "application/pdf"))).toBeNull();
    expect(sizeProblem(sized(10 * 1024 * 1024 + 1, "application/pdf"))).toMatch(/10 MB/);
    expect(sizeProblem(sized(1024 * 1024, "text/markdown"))).toBeNull();
    expect(sizeProblem(sized(1024 * 1024 + 1, "text/markdown"))).toMatch(/1 MB/);
    expect(sizeProblem(sized(19 * 1024 * 1024, "image/png"))).toBeNull();
  });

  it("formats sizes", () => {
    expect(formatBytes(1)).toBe("1 byte");
    expect(formatBytes(1023)).toBe("1023 bytes");
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(1024 * 1024)).toBe("1 MB");
  });

  it("needs a file for file evidence and an https link for links", () => {
    const base = { url: "", file_id: "", note: "" };
    expect(evidenceFormSchema.safeParse({ ...base, kind: "FILE" }).success).toBe(false);
    expect(evidenceFormSchema.safeParse({ ...base, kind: "SCREENSHOT", file_id: "f1" }).success).toBe(true);
    expect(evidenceFormSchema.safeParse({ ...base, kind: "LINK", url: "http://x.io" }).success).toBe(false);
    expect(evidenceFormSchema.safeParse({ ...base, kind: "LINK", url: "https://x.io" }).success).toBe(true);
    expect(
      evidenceFormSchema.safeParse({ ...base, kind: "PR", url: "https://gitlab.com/a/b/pull/1" }).success,
    ).toBe(false);
  });
});
