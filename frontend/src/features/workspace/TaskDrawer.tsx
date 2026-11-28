/**
 * Task drawer (spec §13.5 #30): the task's details, where it may move next and why not,
 * dependencies, evidence and — from the comments step — its conversation. The lead edits and
 * manages dependencies; the assignee or the lead adds evidence; the client only reads (§1.6).
 * Evidence links are shown as plain https links, never fetched or previewed (D148).
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { ExternalLink, Link2, Lock, Trash2 } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { ApiError } from "@/api/client";
import type { TaskCard, TaskDetail } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Badge, Skeleton } from "@/components/ui/Display";
import { Alert, ErrorState } from "@/components/ui/Feedback";
import { Field, FormField } from "@/components/ui/Field";
import { ConfirmDialog, Sheet } from "@/components/ui/Overlay";
import { Select, type Option } from "@/components/ui/Select";
import { toast } from "@/components/ui/toast-store";
import { Comments } from "@/components/Comments";
import { useMe } from "@/features/auth/api";
import { applyFieldErrors, messageFor } from "@/features/auth/errors";
import { formatDate } from "@/lib/format";
import {
  STATUS_LABEL,
  useAddDependency,
  useAddEvidence,
  useDeleteTask,
  useRemoveDependency,
  useTask,
} from "./api";
import { useProjectFiles } from "./filesApi";
import { evidenceFormSchema, type EvidenceForm } from "./schemas";
import { TaskFormDialog } from "./TaskFormDialog";

interface Props {
  projectId: string;
  taskId: string | null;
  onClose: () => void;
  onMove: (task: TaskCard, status: TaskDetail["status"]) => void;
  /** Same-milestone tasks the lead may add as dependencies. */
  candidates: TaskCard[];
  milestones: Option[];
  members: Option[];
  myUserId: string | null;
  /** The project is IN_PROGRESS: conversations are open (D142). */
  writable: boolean;
}

const KIND_LABEL = { FILE: "File", LINK: "Link", PR: "Pull request", SCREENSHOT: "Screenshot" };

export function TaskDrawer({
  projectId,
  taskId,
  onClose,
  onMove,
  candidates,
  milestones,
  members,
  myUserId,
  writable,
}: Props) {
  const q = useTask(taskId);
  return (
    <Sheet
      open={taskId !== null}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={q.data?.title ?? "Task"}
    >
      {q.isPending ? (
        <div className="space-y-3 p-5" aria-busy="true" aria-label="Loading the task">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : q.isError ? (
        <ErrorState
          title={q.error instanceof ApiError && q.error.status === 404 ? "This task is gone" : "The task didn’t load"}
          requestId={q.error instanceof ApiError ? q.error.requestId : null}
          onRetry={() => void q.refetch()}
        />
      ) : (
        <Details
          task={q.data}
          projectId={projectId}
          onClose={onClose}
          onMove={onMove}
          candidates={candidates.filter((c) => c.milestone_id === q.data.milestone_id && c.id !== q.data.id)}
          milestones={milestones}
          members={members}
          myUserId={myUserId}
          writable={writable}
        />
      )}
    </Sheet>
  );
}

function Details({
  task,
  projectId,
  onClose,
  onMove,
  candidates,
  milestones,
  members,
  myUserId,
  writable,
}: Omit<Props, "taskId"> & { task: TaskDetail }) {
  const remove = useDeleteTask(projectId);
  const me = useMe();
  const addDep = useAddDependency(projectId, task.id);
  const removeDep = useRemoveDependency(projectId, task.id);
  const [dep, setDep] = useState<string>("");
  const [editing, setEditing] = useState(false);
  const mayAddEvidence = task.can_edit || (myUserId !== null && task.assignee?.id === myUserId && task.can_move_to.length > 0);
  const milestoneName = milestones.find((m) => m.value === task.milestone_id)?.label ?? "";
  return (
    <div className="space-y-6 p-5">
      <div className="flex flex-wrap items-center gap-2 text-body-sm">
        <Badge tone="info" icon={false}>
          {STATUS_LABEL[task.status]}
        </Badge>
        <span className="text-text-muted">{milestoneName}</span>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-body-sm">
        <dt className="text-text-muted">Assignee</dt>
        <dd>{task.assignee?.name ?? "Nobody yet"}</dd>
        <dt className="text-text-muted">Deadline</dt>
        <dd>{task.deadline ? formatDate(task.deadline) : "None"}</dd>
        <dt className="text-text-muted">Estimate</dt>
        <dd className="tabular">{Number(task.estimate_hours)} hours</dd>
        <dt className="text-text-muted">Created by</dt>
        <dd>{task.created_by.name}</dd>
      </dl>
      {task.description ? (
        <p className="whitespace-pre-wrap break-words text-body text-text">{task.description}</p>
      ) : null}

      {task.can_move_to.length > 0 ? (
        <section aria-labelledby="task-moves">
          <h3 id="task-moves" className="mb-2 text-body-sm font-semibold">
            Move to
          </h3>
          <ul className="space-y-2">
            {task.can_move_to.map((o) => (
              <li key={o.status} className="flex flex-wrap items-center gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!o.allowed}
                  onClick={() => { onMove(task, o.status); }}
                >
                  {STATUS_LABEL[o.status]}
                </Button>
                {o.reason ? <span className="text-caption text-text-muted">{o.reason}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-labelledby="task-deps">
        <h3 id="task-deps" className="mb-2 text-body-sm font-semibold">
          Waits for
        </h3>
        {task.dependencies.length === 0 ? (
          <p className="text-body-sm text-text-muted">No other tasks.</p>
        ) : (
          <ul className="space-y-1 text-body-sm">
            {task.dependencies.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-2">
                <span className="inline-flex min-w-0 items-center gap-1.5">
                  {d.status !== "DONE" ? <Lock className="size-3.5 shrink-0 text-warning" aria-hidden="true" /> : null}
                  <span className="truncate">{d.title}</span>
                  <span className="text-text-muted">({STATUS_LABEL[d.status]})</span>
                </span>
                {task.can_edit ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Stop waiting for ${d.title}`}
                    onClick={() => { removeDep.mutate(d.id, {
                        onError: (e) => toast({ tone: "danger", title: messageFor(e) }),
                      }); }
                    }
                  >
                    <Trash2 className="size-4" aria-hidden="true" />
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {task.dependents.length > 0 ? (
          <p className="mt-2 text-caption text-text-muted">
            {task.dependents.map((d) => d.title).join(", ")} {task.dependents.length === 1 ? "waits" : "wait"} for this task.
          </p>
        ) : null}
        {task.can_edit && candidates.length > 0 ? (
          <div className="mt-3 flex items-end gap-2">
            <FormField label="Add a task it waits for" className="flex-1">
              {(a11y) => (
                <Select
                  {...a11y}
                  value={dep || undefined}
                  onChange={setDep}
                  placeholder="Choose a task"
                  options={candidates.map((c) => ({ value: c.id, label: c.title }))}
                />
              )}
            </FormField>
            <Button
              variant="outline"
              disabled={!dep}
              loading={addDep.isPending}
              onClick={() => { addDep.mutate(dep, {
                  onSuccess: () => { setDep(""); },
                  onError: (e) => toast({ tone: "danger", title: messageFor(e) }),
                }); }
              }
            >
              Add
            </Button>
          </div>
        ) : null}
      </section>

      <section aria-labelledby="task-evidence">
        <h3 id="task-evidence" className="mb-2 text-body-sm font-semibold">
          Evidence
        </h3>
        {task.evidence.length === 0 ? (
          <p className="text-body-sm text-text-muted">Nothing attached yet.</p>
        ) : (
          <ul className="space-y-2 text-body-sm">
            {task.evidence.map((e) => (
              <li key={e.id} className="rounded-md border border-border p-3">
                <p className="flex flex-wrap items-center gap-2">
                  <Badge icon={false}>{KIND_LABEL[e.kind]}</Badge>
                  {e.url ? (
                    <a
                      href={e.url}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      className="inline-flex min-w-0 items-center gap-1 break-all text-primary underline"
                    >
                      {e.url}
                      <ExternalLink className="size-3.5 shrink-0" aria-hidden="true" />
                    </a>
                  ) : (
                    <span className="break-all">{e.file_name}</span>
                  )}
                </p>
                {e.note ? <p className="mt-1 text-text-muted">{e.note}</p> : null}
                <p className="mt-1 text-caption text-text-muted">Added by {e.added_by.name}</p>
              </li>
            ))}
          </ul>
        )}
        {mayAddEvidence ? <EvidenceAdd projectId={projectId} taskId={task.id} /> : null}
      </section>

      <Comments
        targetType="TASK"
        targetId={task.id}
        people={members.map((m) => ({ id: m.value, name: m.label }))}
        me={me.data ? { id: me.data.id, name: me.data.display_name } : null}
        canWrite={writable && me.data?.role !== "ADMIN"}
      />

      {task.can_edit ? (
        <div className="flex flex-wrap gap-2 border-t border-border pt-4">
          <Button variant="outline" onClick={() => { setEditing(true); }}>
            Edit task
          </Button>
          <TaskFormDialog
            projectId={projectId}
            milestones={milestones}
            members={members}
            task={task}
            open={editing}
            onOpenChange={setEditing}
          />
          {task.status !== "DONE" ? (
            <ConfirmDialog
              trigger={<Button variant="destructive">Delete task</Button>}
              title="Delete this task?"
              description="It leaves the board for everyone. Tasks with evidence stay."
              confirmLabel="Delete task"
              onConfirm={async () => {
                try {
                  await remove.mutateAsync(task);
                  toast({ tone: "success", title: "Task deleted" });
                  onClose();
                } catch (e) {
                  toast({ tone: "danger", title: messageFor(e) });
                }
              }}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function EvidenceAdd({ projectId, taskId }: { projectId: string; taskId: string }) {
  const add = useAddEvidence(projectId, taskId);
  const files = useProjectFiles(projectId);
  const [notice, setNotice] = useState<string | null>(null);
  const form = useForm<EvidenceForm>({
    resolver: zodResolver(evidenceFormSchema),
    defaultValues: { kind: "LINK", url: "", file_id: "", note: "" },
  });
  const kind = form.watch("kind");
  const usesFile = kind === "FILE" || kind === "SCREENSHOT";
  // The first page (newest 20) is enough to pick from; older files are on the Files tab.
  const choices: Option[] = (files.data?.pages[0]?.items ?? [])
    .filter((f) => kind !== "SCREENSHOT" || f.mime.startsWith("image/"))
    .map((f) => ({ value: f.id, label: f.name }));
  const submit = form.handleSubmit(async (v) => {
    setNotice(null);
    try {
      await add.mutateAsync(
        usesFile
          ? { kind: v.kind, file_id: v.file_id, note: v.note || null }
          : { kind: v.kind, url: v.url, note: v.note || null },
      );
      form.reset();
      toast({ tone: "success", title: "Evidence added" });
    } catch (e) {
      if (!applyFieldErrors(e, form.setError, ["url", "file_id", "note"])) setNotice(messageFor(e));
    }
  });
  return (
    <form noValidate onSubmit={(e) => void submit(e)} className="mt-4 space-y-3 rounded-lg bg-surface-2 p-3">
      {notice ? <Alert tone="danger">{notice}</Alert> : null}
      <FormField label="Kind">
        {(a11y) => (
          <Controller
            control={form.control}
            name="kind"
            render={({ field }) => (
              <Select
                {...a11y}
                value={field.value}
                onChange={field.onChange}
                options={[
                  { value: "LINK", label: "Link" },
                  { value: "PR", label: "Pull request" },
                  { value: "FILE", label: "File" },
                  { value: "SCREENSHOT", label: "Screenshot" },
                ]}
              />
            )}
          />
        )}
      </FormField>
      {usesFile ? (
        choices.length === 0 ? (
          <p className="text-body-sm text-text-muted">
            {kind === "SCREENSHOT"
              ? "Upload an image to the project’s Files first."
              : "Upload a file to the project’s Files first."}
          </p>
        ) : (
          <FormField label="File" error={form.formState.errors.file_id?.message}>
            {(a11y) => (
              <Controller
                control={form.control}
                name="file_id"
                render={({ field }) => (
                  <Select
                    {...a11y}
                    value={field.value || undefined}
                    onChange={field.onChange}
                    placeholder="Choose a file"
                    options={choices}
                  />
                )}
              />
            )}
          </FormField>
        )
      ) : (
        <Field
          label="Link"
          type="url"
          inputMode="url"
          placeholder="https://"
          error={form.formState.errors.url?.message}
          {...form.register("url")}
        />
      )}
      <Field label="Note (optional)" error={form.formState.errors.note?.message} {...form.register("note")} />
      <Button type="submit" variant="outline" loading={form.formState.isSubmitting}>
        <Link2 className="size-4" aria-hidden="true" /> Add evidence
      </Button>
    </form>
  );
}
