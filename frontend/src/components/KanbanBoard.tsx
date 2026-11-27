/**
 * Kanban board (spec §13.5 #30, §13.6, §13.14; D143, D158). Four columns (To do, In progress,
 * Review, Done) with counts; cards show the assignee, deadline (danger when overdue), estimate,
 * difficulty, a lock while dependencies are open, and evidence and comment counts.
 *
 * Moving a card: drag it with a mouse, long-press (300 ms) and drag on a touch screen, or pick it
 * up with its handle and the keyboard (Space, arrows, Space); screen readers hear where it went.
 * Every card also has a "Move to…" menu, so moving never depends on dragging. A refused target
 * says why ("Move it to Review first") instead of silently snapping back. Read-only viewers (the
 * client, §1.6) get no handles and no menus. On phones the board shows one column per screen
 * with snap scrolling and column tabs.
 */
import {
  closestCorners,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  CalendarClock,
  GripVertical,
  Lock,
  MessageSquare,
  MoreHorizontal,
  Paperclip,
} from "lucide-react";
import { useRef, useState } from "react";
import type { TaskCard, TaskStatus } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Avatar, Badge } from "@/components/ui/Display";
import { DropdownMenu } from "@/components/ui/Overlay";
import { timing } from "@/design/motion";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";

export interface KanbanColumn {
  status: TaskStatus;
  label: string;
  cards: TaskCard[];
  hasMore: boolean;
  loadingMore: boolean;
  onShowMore: () => void;
}

export interface KanbanMove {
  card: TaskCard;
  status: TaskStatus;
  afterId: string | null;
  beforeId: string | null;
}

interface KanbanBoardProps {
  columns: KanbanColumn[];
  /** No handles or menus at all (the client). */
  readOnly: boolean;
  /** Whether the viewer may move this card (its assignee or the lead). */
  canMove: (card: TaskCard) => boolean;
  /** Why moving `card` to `target` is refused, or null if the board may try. */
  refusal: (card: TaskCard, target: TaskStatus) => string | null;
  onMove: (move: KanbanMove) => void;
  onRefused: (reason: string) => void;
  onOpen: (card: TaskCard) => void;
  /** Today in Asia/Dhaka as YYYY-MM-DD (overdue deadlines). */
  today: string;
}

const COLUMN_ID = (s: TaskStatus) => `column:${s}`;
const HOURS = new Intl.NumberFormat("en", { maximumFractionDigits: 1 });
const DIFFICULTY: Record<TaskCard["difficulty"], string> = {
  EASY: "Easy",
  MEDIUM: "Medium",
  HARD: "Hard",
};

/** Where a card dropped "over" something lands: the neighbours in the target column. */
export function dropPlace(
  column: TaskCard[],
  activeId: string,
  overId: string | null,
  fromSameColumn: boolean,
): { afterId: string | null; beforeId: string | null } {
  const rest = column.filter((c) => c.id !== activeId);
  if (overId === null) {
    return { afterId: rest.at(-1)?.id ?? null, beforeId: null };
  }
  const overIndex = rest.findIndex((c) => c.id === overId);
  if (overIndex < 0) return { afterId: rest.at(-1)?.id ?? null, beforeId: null };
  const activeIndex = column.findIndex((c) => c.id === activeId);
  const overOriginal = column.findIndex((c) => c.id === overId);
  const below = fromSameColumn && activeIndex >= 0 && activeIndex < overOriginal;
  const index = below ? overIndex + 1 : overIndex;
  return { afterId: rest[index - 1]?.id ?? null, beforeId: rest[index]?.id ?? null };
}

function TaskTile({
  card,
  draggable,
  menu,
  onOpen,
  today,
}: {
  card: TaskCard;
  draggable: boolean;
  menu: React.ReactNode;
  onOpen: () => void;
  today: string;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id: card.id, data: { status: card.status }, disabled: !draggable });
  const overdue = card.deadline !== null && card.deadline < today && card.status !== "DONE";
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "relative flex items-stretch rounded-lg border border-border bg-surface shadow-xs",
        isDragging && "z-10 shadow-lg",
      )}
      data-testid="task-card"
    >
      {draggable ? (
        <button
          type="button"
          ref={setActivatorNodeRef}
          {...attributes}
          {...listeners}
          aria-label={`Move ${card.title}`}
          className="flex w-8 shrink-0 cursor-grab touch-none items-center justify-center rounded-l-lg text-text-subtle hover:bg-surface-2 hover:text-text active:cursor-grabbing"
        >
          <GripVertical className="size-4" aria-hidden="true" />
        </button>
      ) : null}
      <div className="min-w-0 flex-1 p-3">
        <div className="flex items-start justify-between gap-2">
          <button
            type="button"
            onClick={onOpen}
            className="min-h-11 min-w-0 flex-1 text-left font-medium text-text hover:text-primary"
          >
            <span className="line-clamp-2 break-words">{card.title}</span>
          </button>
          {menu}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-caption text-text-muted">
          {card.assignee ? (
            <span className="inline-flex items-center gap-1.5">
              <Avatar name={card.assignee.name} size="sm" />
              <span className="max-w-32 truncate">{card.assignee.name}</span>
            </span>
          ) : (
            <span>Unassigned</span>
          )}
          {card.deadline ? (
            <span
              className={cn("inline-flex items-center gap-1", overdue && "font-medium text-danger")}
            >
              <CalendarClock className="size-3.5" aria-hidden="true" />
              {overdue ? "Overdue: " : "Due "}
              {formatDate(card.deadline)}
            </span>
          ) : null}
          <span className="tabular">{HOURS.format(Number(card.estimate_hours))} h</span>
          <span>{DIFFICULTY[card.difficulty]}</span>
          {card.blocked_by > 0 ? (
            <Badge tone="warning" icon={false} className="gap-1">
              <Lock className="size-3.5" aria-hidden="true" />
              Waiting for {card.blocked_by} {card.blocked_by === 1 ? "task" : "tasks"}
            </Badge>
          ) : null}
          {card.evidence_count > 0 ? (
            <span className="inline-flex items-center gap-1">
              <Paperclip className="size-3.5" aria-hidden="true" />
              <span className="sr-only">Evidence: </span>
              {card.evidence_count}
            </span>
          ) : null}
          {card.comment_count > 0 ? (
            <span className="inline-flex items-center gap-1">
              <MessageSquare className="size-3.5" aria-hidden="true" />
              <span className="sr-only">Comments: </span>
              {card.comment_count}
            </span>
          ) : null}
        </div>
      </div>
    </li>
  );
}

function Column({
  column,
  children,
  refusedReason,
}: {
  column: KanbanColumn;
  children: React.ReactNode;
  refusedReason: string | null;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: COLUMN_ID(column.status) });
  const headingId = `kanban-${column.status}`;
  return (
    <section
      ref={setNodeRef}
      aria-labelledby={headingId}
      data-column={column.status}
      className={cn(
        "flex w-[calc(100vw-2rem)] shrink-0 snap-start flex-col rounded-xl border border-border bg-surface-2 p-3 md:w-auto md:shrink",
        isOver && refusedReason === null && "border-primary",
        isOver && refusedReason !== null && "border-danger",
      )}
    >
      <h2 id={headingId} className="mb-3 flex items-center justify-between text-body-sm font-semibold">
        {column.label}
        <span className="tabular rounded-full bg-surface px-2 text-caption text-text-muted">
          {column.cards.length}
          {column.hasMore ? "+" : ""}
        </span>
      </h2>
      {isOver && refusedReason ? (
        <p role="status" className="mb-2 rounded-md bg-danger-bg px-2 py-1 text-caption text-danger">
          {refusedReason}
        </p>
      ) : null}
      {children}
      {column.hasMore ? (
        <Button
          variant="ghost"
          size="sm"
          className="mt-2"
          loading={column.loadingMore}
          onClick={column.onShowMore}
        >
          Show more
        </Button>
      ) : null}
    </section>
  );
}

export function KanbanBoard({
  columns,
  readOnly,
  canMove,
  refusal,
  onMove,
  onRefused,
  onOpen,
  today,
}: KanbanBoardProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: timing.boardHoldMs, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const [over, setOver] = useState<{ status: TaskStatus; reason: string | null } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const cards = columns.flatMap((c) => c.cards);
  const cardOf = (id: string | number) => cards.find((c) => c.id === String(id));
  const statusOf = (id: string | number | null | undefined): TaskStatus | null => {
    if (id === null || id === undefined) return null;
    const key = String(id);
    if (key.startsWith("column:")) return key.slice(7) as TaskStatus;
    return cardOf(key)?.status ?? null;
  };
  const labelOf = (s: TaskStatus | null) => columns.find((c) => c.status === s)?.label ?? "";

  const onDragOver = (e: DragOverEvent) => {
    const card = cardOf(e.active.id);
    const target = statusOf(e.over?.id);
    if (!card || !target) {
      setOver(null);
      return;
    }
    setOver({ status: target, reason: target === card.status ? null : refusal(card, target) });
  };

  const onDragEnd = (e: DragEndEvent) => {
    setOver(null);
    const card = cardOf(e.active.id);
    const target = statusOf(e.over?.id);
    if (!card || !target || !e.over) return;
    const reason = target === card.status ? null : refusal(card, target);
    if (reason) {
      onRefused(reason);
      return;
    }
    const column = columns.find((c) => c.status === target)?.cards ?? [];
    const overId = String(e.over.id).startsWith("column:") ? null : String(e.over.id);
    if (overId === card.id) return;
    const place = dropPlace(column, card.id, overId, target === card.status);
    onMove({ card, status: target, ...place });
  };

  const moveMenu = (card: TaskCard) => (
    <DropdownMenu
      label="Move to…"
      trigger={
        <button
          type="button"
          aria-label={`Move ${card.title} to another column`}
          className="-mr-1 -mt-1 flex size-11 shrink-0 items-center justify-center rounded-md text-text-muted hover:bg-surface-2 hover:text-text"
        >
          <MoreHorizontal className="size-5" aria-hidden="true" />
        </button>
      }
      items={columns
        .filter((c) => c.status !== card.status)
        .map((c) => ({
          label: `Move to ${c.label}`,
          onSelect: () => {
            const reason = refusal(card, c.status);
            if (reason) onRefused(reason);
            else onMove({ card, status: c.status, afterId: c.cards.at(-1)?.id ?? null, beforeId: null });
          },
        }))}
    />
  );

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
      onDragCancel={() => { setOver(null); }}
      accessibility={{
        announcements: {
          onDragStart: ({ active }) => `Picked up ${cardOf(active.id)?.title ?? "the task"}.`,
          onDragOver: ({ active, over: o }) => {
            const card = cardOf(active.id);
            const target = statusOf(o?.id);
            if (!card || !target) return `${card?.title ?? "The task"} is not over a column.`;
            const reason = target === card.status ? null : refusal(card, target);
            return reason
              ? `${labelOf(target)}: ${reason}`
              : `${card.title} is over ${labelOf(target)}.`;
          },
          onDragEnd: ({ active, over: o }) =>
            o
              ? `${cardOf(active.id)?.title ?? "The task"} dropped in ${labelOf(statusOf(o.id))}.`
              : `${cardOf(active.id)?.title ?? "The task"} put back.`,
          onDragCancel: ({ active }) => `Moving ${cardOf(active.id)?.title ?? "the task"} was cancelled.`,
        },
        screenReaderInstructions: {
          draggable:
            "To move a task, press Space or Enter on its handle, use the arrow keys to choose a column and place, then press Space or Enter to drop it. Press Escape to cancel. Each task also has a Move to menu.",
        },
      }}
    >
      <nav aria-label="Board columns" className="mb-3 flex gap-2 overflow-x-auto md:hidden">
        {columns.map((c) => (
          <Button
            key={c.status}
            variant="outline"
            size="sm"
            onClick={() =>
              scroller.current
                ?.querySelector(`[data-column="${c.status}"]`)
                ?.scrollIntoView({ inline: "start", block: "nearest" })
            }
          >
            {c.label} <span className="tabular text-text-muted">{c.cards.length}</span>
          </Button>
        ))}
      </nav>
      <div
        ref={scroller}
        className="-mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-2 md:mx-0 md:grid md:grid-cols-4 md:overflow-visible md:px-0"
      >
        {columns.map((column) => (
          <Column
            key={column.status}
            column={column}
            refusedReason={over?.status === column.status ? over.reason : null}
          >
            <SortableContext
              id={COLUMN_ID(column.status)}
              items={column.cards.map((c) => c.id)}
              strategy={verticalListSortingStrategy}
            >
              <ul className="flex min-h-16 flex-col gap-2" aria-label={`${column.label} tasks`}>
                {column.cards.map((card) => (
                  <TaskTile
                    key={card.id}
                    card={card}
                    draggable={!readOnly && canMove(card)}
                    menu={!readOnly && canMove(card) ? moveMenu(card) : null}
                    onOpen={() => { onOpen(card); }}
                    today={today}
                  />
                ))}
              </ul>
            </SortableContext>
            {column.cards.length === 0 ? (
              <p className="py-4 text-center text-caption text-text-muted">No tasks here.</p>
            ) : null}
          </Column>
        ))}
      </div>
    </DndContext>
  );
}
