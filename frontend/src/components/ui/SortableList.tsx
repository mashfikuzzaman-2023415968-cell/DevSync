/**
 * Reorderable list (spec §13.3; @dnd-kit, D29): drag with a pointer or touch, or pick up an item
 * with the handle and move it with the arrow keys; screen readers hear where it went. A
 * "Move up / Move down" menu in each row (rendered by the caller) covers everyone else.
 */
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";
import type { ReactNode } from "react";
import { timing } from "@/design/motion";
import { cn } from "@/lib/cn";

interface SortableListProps<T extends { id: string }> {
  items: T[];
  /** Called with the new order of ids. */
  onReorder: (ids: string[]) => void;
  label: (item: T) => string;
  renderItem: (item: T, index: number) => ReactNode;
  disabled?: boolean;
}

function Row({
  id,
  name,
  disabled,
  children,
}: {
  id: string;
  name: string;
  disabled: boolean;
  children: ReactNode;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id, disabled });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "relative flex items-stretch gap-1 rounded-lg border border-border bg-surface shadow-xs",
        isDragging && "z-10 shadow-lg",
      )}
    >
      <button
        type="button"
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        aria-label={`Reorder ${name}`}
        disabled={disabled}
        className="flex w-11 shrink-0 cursor-grab touch-none items-center justify-center rounded-l-lg text-text-subtle hover:bg-surface-2 hover:text-text active:cursor-grabbing disabled:cursor-not-allowed"
      >
        <GripVertical className="size-5" aria-hidden="true" />
      </button>
      <div className="min-w-0 flex-1">{children}</div>
    </li>
  );
}

export function SortableList<T extends { id: string }>({
  items,
  onReorder,
  label,
  renderItem,
  disabled = false,
}: SortableListProps<T>) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: timing.dragHoldMs, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const ids = items.map((i) => i.id);
  const nameOf = (id: string | number) => {
    const item = items.find((i) => i.id === id);
    return item ? label(item) : "item";
  };
  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = ids.indexOf(String(active.id));
    const to = ids.indexOf(String(over.id));
    if (from < 0 || to < 0) return;
    onReorder(arrayMove(ids, from, to));
  };
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={onDragEnd}
      accessibility={{
        announcements: {
          onDragStart: ({ active }) => `Picked up ${nameOf(active.id)}.`,
          onDragOver: ({ active, over }) =>
            over
              ? `${nameOf(active.id)} is now at position ${String(ids.indexOf(String(over.id)) + 1)} of ${String(ids.length)}.`
              : `${nameOf(active.id)} is no longer over the list.`,
          onDragEnd: ({ active, over }) =>
            over
              ? `${nameOf(active.id)} dropped at position ${String(ids.indexOf(String(over.id)) + 1)} of ${String(ids.length)}.`
              : `${nameOf(active.id)} put back.`,
          onDragCancel: ({ active }) => `Moving ${nameOf(active.id)} was cancelled.`,
        },
        screenReaderInstructions: {
          draggable:
            "To move an item, press Space or Enter, use the arrow keys, then press Space or Enter again to drop it. Press Escape to cancel.",
        },
      }}
    >
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        <ol className="space-y-3">
          {items.map((item, index) => (
            <Row key={item.id} id={item.id} name={label(item)} disabled={disabled}>
              {renderItem(item, index)}
            </Row>
          ))}
        </ol>
      </SortableContext>
    </DndContext>
  );
}
