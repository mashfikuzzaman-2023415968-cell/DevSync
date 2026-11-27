/** KanbanBoard (screen 30; D143, D158): columns with counts, the "Move to…" path, refused targets
 * that say why, no handles or menus for read-only viewers, overdue deadlines, and where a drop
 * lands between two cards. */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { TaskCard } from "@/api/types";
import { dropPlace, KanbanBoard, type KanbanColumn } from "./KanbanBoard";

const card = (id: string, over: Partial<TaskCard> = {}): TaskCard => ({
  id,
  milestone_id: "m1",
  title: `Task ${id}`,
  status: "TODO",
  assignee: { id: "u1", name: "Nusrat Jahan" },
  deadline: null,
  estimate_hours: "8.0",
  difficulty: "MEDIUM",
  position: id,
  progress_pct: 0,
  blocked_by: 0,
  evidence_count: 0,
  comment_count: 0,
  last_activity_at: "2026-11-20T05:00:00Z",
  version: 1,
  ...over,
});

const columns = (todo: TaskCard[], doing: TaskCard[] = []): KanbanColumn[] =>
  (
    [
      ["TODO", "To do", todo],
      ["IN_PROGRESS", "In progress", doing],
      ["REVIEW", "Review", []],
      ["DONE", "Done", []],
    ] as const
  ).map(([status, label, cards]) => ({
    status,
    label,
    cards: [...cards],
    hasMore: false,
    loadingMore: false,
    onShowMore: vi.fn(),
  }));

function board(props: Partial<Parameters<typeof KanbanBoard>[0]> = {}) {
  const handlers = { onMove: vi.fn(), onRefused: vi.fn(), onOpen: vi.fn() };
  render(
    <KanbanBoard
      columns={columns([card("a"), card("b", { deadline: "2026-11-01" })])}
      readOnly={false}
      canMove={() => true}
      refusal={(_c, t) => (t === "DONE" ? "Move it to In progress first." : null)}
      today="2026-11-20"
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

describe("KanbanBoard", () => {
  it("shows four columns with their counts", () => {
    board();
    for (const name of [/^To do/, /^In progress/, /^Review/, /^Done/]) {
      expect(screen.getByRole("region", { name })).toBeInTheDocument();
    }
    const todo = screen.getByRole("region", { name: /To do/ });
    expect(within(todo).getAllByTestId("task-card")).toHaveLength(2);
    expect(within(todo).getByText("2")).toBeInTheDocument();
  });

  it("marks an overdue deadline", () => {
    board();
    expect(screen.getByText(/Overdue:/)).toBeInTheDocument();
  });

  it("moves with the menu, to the end of the target column", async () => {
    const h = board({ columns: columns([card("a")], [card("x", { status: "IN_PROGRESS" })]) });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Move Task a to another column" }));
    await user.click(await screen.findByRole("menuitem", { name: "Move to In progress" }));
    expect(h.onMove).toHaveBeenCalledWith(
      expect.objectContaining({ status: "IN_PROGRESS", afterId: "x", beforeId: null }),
    );
  });

  it("says why a target is refused instead of moving", async () => {
    const h = board();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Move Task a to another column" }));
    await user.click(await screen.findByRole("menuitem", { name: "Move to Done" }));
    expect(h.onRefused).toHaveBeenCalledWith("Move it to In progress first.");
    expect(h.onMove).not.toHaveBeenCalled();
  });

  it("gives read-only viewers no handles and no menus", () => {
    board({ readOnly: true });
    expect(screen.queryByRole("button", { name: /^Move Task/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /another column/ })).not.toBeInTheDocument();
  });

  it("gives handles only on the cards the viewer may move", () => {
    board({ canMove: (c) => c.id === "a" });
    expect(screen.getByRole("button", { name: "Move Task a" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Move Task b" })).not.toBeInTheDocument();
  });

  it("opens a card", async () => {
    const h = board();
    await userEvent.setup().click(screen.getByRole("button", { name: "Task a" }));
    expect(h.onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "a" }));
  });
});

describe("dropPlace", () => {
  const col = [card("a"), card("b"), card("c")];
  it("drops at the end of a column when not over a card", () => {
    expect(dropPlace(col, "z", null, false)).toEqual({ afterId: "c", beforeId: null });
    expect(dropPlace([], "z", null, false)).toEqual({ afterId: null, beforeId: null });
  });
  it("drops above the card it is over when coming from another column", () => {
    expect(dropPlace(col, "z", "b", false)).toEqual({ afterId: "a", beforeId: "b" });
    expect(dropPlace(col, "z", "a", false)).toEqual({ afterId: null, beforeId: "a" });
  });
  it("moving down in its own column lands below the card it is over", () => {
    expect(dropPlace(col, "a", "b", true)).toEqual({ afterId: "b", beforeId: "c" });
    expect(dropPlace(col, "a", "c", true)).toEqual({ afterId: "c", beforeId: null });
  });
  it("moving up in its own column lands above the card it is over", () => {
    expect(dropPlace(col, "c", "a", true)).toEqual({ afterId: null, beforeId: "a" });
  });
});
