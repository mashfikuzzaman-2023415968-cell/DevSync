/**
 * Files tab `/w/:projectId/files` (spec §13.5 #35; D147): upload (participants, while the project
 * is in progress) and the list, newest first, with who uploaded each file, its size, the tasks
 * that use it as evidence, download and delete (the uploader or the lead). Names are shown as
 * text; downloads go through the API's short-lived link and always save as attachments.
 */
import { Download, FileText, Image as ImageIcon, Trash2 } from "lucide-react";
import { useState } from "react";
import { ApiError, fileUrl } from "@/api/client";
import type { ProjectFile } from "@/api/types";
import { VirtualList } from "@/components/VirtualList";
import { Button, IconButton } from "@/components/ui/Button";
import { Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { ConfirmDialog } from "@/components/ui/Overlay";
import { toast } from "@/components/ui/toast-store";
import { messageFor } from "@/features/auth/errors";
import { formatBytes, formatDate } from "@/lib/format";
import { useWorkspace } from "./context";
import {
  PROJECT_FILE_RULE,
  sizeProblem,
  useDeleteFile,
  useProjectFiles,
  useUploadFile,
} from "./filesApi";

export default function FilesTab() {
  const ws = useWorkspace();
  const q = useProjectFiles(ws.projectId);
  const open = ws.team.project_status === "IN_PROGRESS";
  const canUpload = open && (ws.isClient || ws.myUserId !== null);
  return (
    <div className="space-y-6">
      {canUpload ? <UploadCard projectId={ws.projectId} /> : null}
      {q.isPending ? (
        <div className="space-y-3" aria-busy="true" aria-label="Loading files">
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
        </div>
      ) : q.isError ? (
        <Card>
          <ErrorState
            title="Files didn’t load"
            requestId={q.error instanceof ApiError ? q.error.requestId : null}
            onRetry={() => void q.refetch()}
          />
        </Card>
      ) : (
        <FileList
          projectId={ws.projectId}
          files={q.data.pages.flatMap((p) => p.items)}
          canUpload={canUpload}
          more={q.hasNextPage}
          loadingMore={q.isFetchingNextPage}
          onMore={() => void q.fetchNextPage()}
        />
      )}
    </div>
  );
}

function UploadCard({ projectId }: { projectId: string }) {
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | undefined>(undefined);
  const [done, setDone] = useState(0);
  const send = useUploadFile(projectId, setProgress);
  const onFile = (file: File) => {
    const problem = sizeProblem(file);
    setError(problem ?? undefined);
    if (problem) return;
    setProgress(0);
    send.mutate(file, {
      onSuccess: (stored) => {
        toast({ tone: "success", title: `Uploaded ${stored.name}` });
        setDone((n) => n + 1);
      },
      onError: (e) => {
        setError(messageFor(e));
      },
      onSettled: () => {
        setProgress(null);
      },
    });
  };
  return (
    <Card>
      <CardHeader
        title="Upload a file"
        description="Everyone on the project can see and download it. Images are re-saved without their location data."
      />
      <div className="px-5 pb-5">
        <FileDropzone
          label="Choose a file to upload"
          rule={PROJECT_FILE_RULE}
          onFile={onFile}
          progress={progress}
          error={error}
          resetKey={done}
        />
      </div>
    </Card>
  );
}

interface ListProps {
  projectId: string;
  files: ProjectFile[];
  canUpload: boolean;
  more: boolean;
  loadingMore: boolean;
  onMore: () => void;
}

function FileList({ projectId, files, canUpload, more, loadingMore, onMore }: ListProps) {
  if (files.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={<FileText />}
          title="No files yet"
          description={
            canUpload
              ? "Share designs, specs and notes here; tasks can then use them as evidence."
              : "Files the team shares will appear here."
          }
        />
      </Card>
    );
  }
  return (
    <section aria-labelledby="files-heading" className="space-y-3">
      <h2 id="files-heading" className="text-body font-semibold">
        Project files
      </h2>
      <VirtualList
        items={files}
        getKey={(f) => f.id}
        estimate={96}
        gap={12}
        render={(f) => <FileRow projectId={projectId} file={f} />}
      />
      {more ? (
        <Button variant="outline" loading={loadingMore} onClick={onMore}>
          Show older files
        </Button>
      ) : null}
    </section>
  );
}

function FileRow({ projectId, file }: { projectId: string; file: ProjectFile }) {
  const remove = useDeleteFile(projectId);
  const Icon = file.mime.startsWith("image/") ? ImageIcon : FileText;
  return (
    <Card className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="break-all font-medium text-text">{file.name}</p>
        <p className="text-caption text-text-muted">
          {file.uploaded_by.name}, {formatDate(file.created_at)}, {formatBytes(file.size_bytes)}
        </p>
        {file.links.length > 0 ? (
          <p className="mt-1 text-caption text-text-muted">
            Evidence for{" "}
            {file.links.map((l, i) => (
              <span key={l.task_id}>
                {i > 0 ? ", " : ""}
                <span className="text-text">{l.task_title}</span> ({l.milestone_title})
              </span>
            ))}
          </p>
        ) : null}
      </div>
      <div className="flex gap-2">
        <Button asChild variant="outline" size="sm" className="flex-1 sm:flex-none">
          <a href={fileUrl(file.id)} download aria-label={`Download ${file.name}`}>
            <Download className="size-4" aria-hidden="true" /> Download
          </a>
        </Button>
        {file.can_delete ? (
          <ConfirmDialog
            trigger={
              <IconButton aria-label={`Delete ${file.name}`}>
                <Trash2 />
              </IconButton>
            }
            title={`Delete ${file.name}?`}
            description="It disappears from Files for everyone and can’t be downloaded any more. Tasks that used it keep a note that it was attached."
            confirmLabel="Delete file"
            onConfirm={async () => {
              try {
                await remove.mutateAsync(file.id);
                toast({ tone: "success", title: "File deleted" });
              } catch (e) {
                toast({ tone: "danger", title: messageFor(e) });
              }
            }}
          />
        ) : null}
      </div>
    </Card>
  );
}
