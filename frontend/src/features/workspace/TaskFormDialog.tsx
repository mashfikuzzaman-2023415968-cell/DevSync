/**
 * The lead's task form (spec §13.5 #30 "new-task form for lead"; D143): create a task, or edit
 * one (title, description, assignee, deadline, estimate, difficulty, milestone). Field errors from
 * the server land on their fields; anything else shows above the form.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useState, type ReactNode } from "react";
import { Controller, useForm } from "react-hook-form";
import type { TaskDetail } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Feedback";
import { Field, FormField, Textarea } from "@/components/ui/Field";
import { Dialog } from "@/components/ui/Overlay";
import { Select, type Option } from "@/components/ui/Select";
import { toast } from "@/components/ui/toast-store";
import { applyFieldErrors, messageFor } from "@/features/auth/errors";
import { useCreateTask, usePatchTask } from "./api";
import { taskFormSchema, type TaskForm } from "./schemas";

const DIFFICULTIES: Option[] = [
  { value: "EASY", label: "Easy" },
  { value: "MEDIUM", label: "Medium" },
  { value: "HARD", label: "Hard" },
];
const NOBODY = "none";

interface Props {
  projectId: string;
  milestones: Option[];
  members: Option[];
  trigger?: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Edit this task instead of creating one. */
  task?: TaskDetail | undefined;
  defaultMilestoneId?: string | undefined;
}

export function TaskFormDialog({
  projectId,
  milestones,
  members,
  trigger,
  open,
  onOpenChange,
  task,
  defaultMilestoneId,
}: Props) {
  const create = useCreateTask(projectId);
  const patch = usePatchTask(projectId);
  const [notice, setNotice] = useState<string | null>(null);
  const [inner, setInner] = useState(false);
  const isOpen = open ?? inner;
  const setOpen = onOpenChange ?? setInner;
  const form = useForm<TaskForm>({
    resolver: zodResolver(taskFormSchema),
    values: {
      milestone_id: task?.milestone_id ?? defaultMilestoneId ?? milestones[0]?.value ?? "",
      title: task?.title ?? "",
      description: task?.description ?? "",
      assignee_id: task?.assignee?.id ?? NOBODY,
      deadline: task?.deadline ?? "",
      estimate_hours: task ? String(Number(task.estimate_hours)) : "",
      difficulty: task?.difficulty ?? "MEDIUM",
    },
  });
  const submit = form.handleSubmit(async (v) => {
    setNotice(null);
    const fields = {
      title: v.title,
      description: v.description,
      assignee_id: v.assignee_id === NOBODY ? null : v.assignee_id,
      deadline: v.deadline || null,
      estimate_hours: v.estimate_hours,
      difficulty: v.difficulty,
    };
    try {
      if (task) {
        await patch.mutateAsync({
          task,
          body: {
            ...fields,
            ...(v.milestone_id !== task.milestone_id ? { milestone_id: v.milestone_id } : {}),
          },
        });
        toast({ tone: "success", title: "Task saved" });
      } else {
        await create.mutateAsync({ milestoneId: v.milestone_id, body: fields });
        toast({ tone: "success", title: "Task created" });
        form.reset();
      }
      setOpen(false);
    } catch (e) {
      const keys = [
        "title",
        "description",
        "assignee_id",
        "deadline",
        "estimate_hours",
        "milestone_id",
      ] as const;
      if (!applyFieldErrors(e, form.setError, [...keys])) setNotice(messageFor(e));
    }
  });
  const errors = form.formState.errors;
  return (
    <Dialog
      open={isOpen}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setNotice(null);
      }}
      trigger={trigger}
      title={task ? "Edit task" : "New task"}
      description={
        task ? undefined : "It starts in To do. Only you, the lead, can change it later."
      }
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => {
              setOpen(false);
            }}
          >
            Cancel
          </Button>
          <Button type="submit" form="task-form" loading={form.formState.isSubmitting}>
            {task ? "Save task" : "Create task"}
          </Button>
        </>
      }
    >
      <form id="task-form" noValidate onSubmit={(e) => void submit(e)} className="space-y-4">
        {notice ? <Alert tone="danger">{notice}</Alert> : null}
        <Field label="Title" required error={errors.title?.message} {...form.register("title")} />
        <FormField label="Milestone" required error={errors.milestone_id?.message}>
          {(a11y) => (
            <Controller
              control={form.control}
              name="milestone_id"
              render={({ field }) => (
                <Select
                  {...a11y}
                  value={field.value}
                  onChange={field.onChange}
                  options={milestones}
                />
              )}
            />
          )}
        </FormField>
        <FormField label="Assignee" error={errors.assignee_id?.message}>
          {(a11y) => (
            <Controller
              control={form.control}
              name="assignee_id"
              render={({ field }) => (
                <Select
                  {...a11y}
                  value={field.value}
                  onChange={field.onChange}
                  options={[{ value: NOBODY, label: "Nobody yet" }, ...members]}
                />
              )}
            />
          )}
        </FormField>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field
            label="Estimate (hours)"
            required
            inputMode="decimal"
            error={errors.estimate_hours?.message}
            {...form.register("estimate_hours")}
          />
          <FormField label="Difficulty" required>
            {(a11y) => (
              <Controller
                control={form.control}
                name="difficulty"
                render={({ field }) => (
                  <Select
                    {...a11y}
                    value={field.value}
                    onChange={field.onChange}
                    options={DIFFICULTIES}
                  />
                )}
              />
            )}
          </FormField>
          <Field
            label="Deadline"
            type="date"
            error={errors.deadline?.message}
            {...form.register("deadline")}
          />
        </div>
        <FormField label="Description" error={errors.description?.message}>
          <Textarea rows={4} maxLength={5000} {...form.register("description")} />
        </FormField>
      </form>
    </Dialog>
  );
}
