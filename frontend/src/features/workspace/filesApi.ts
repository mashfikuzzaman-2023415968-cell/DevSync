/** Project file hooks (spec §10.2 Files; D147): the list, 20 at a time with "Show more", upload
 * with progress, and soft delete. Uploading or deleting also refreshes the task drawers, which
 * list files as evidence choices. */
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, upload } from "@/api/client";
import type { ProjectFile, ProjectFilePage } from "@/api/types";
import type { FileRule } from "@/components/ui/FileDropzone";

export const fileKeys = {
  list: (projectId: string) => ["projects", projectId, "files"] as const,
};

const MB = 1024 * 1024;

/** §14.9 exactly; the server checks the content again and decides. */
export const PROJECT_FILE_RULE: FileRule = {
  types: [
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "image/png",
    "image/jpeg",
    "image/webp",
  ],
  maxBytes: 20 * MB,
  description: "PDF up to 10 MB, text or Markdown up to 1 MB, or a PNG, JPEG or WebP image",
};

/** The per-type limits the server applies, checked early for a quicker answer. */
export function sizeProblem(file: File): string | null {
  if (file.type === "application/pdf" && file.size > 10 * MB)
    return "A PDF can be at most 10 MB.";
  if (file.type.startsWith("text/") && file.size > MB)
    return "A text or Markdown file can be at most 1 MB.";
  return null;
}

export function useProjectFiles(projectId: string) {
  return useInfiniteQuery({
    queryKey: fileKeys.list(projectId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api<ProjectFilePage>(
        `/projects/${projectId}/files${pageParam ? `?cursor=${encodeURIComponent(pageParam)}` : ""}`,
      ),
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: 30_000,
  });
}

export function useUploadFile(projectId: string, onProgress: (fraction: number) => void) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return upload<ProjectFile>(`/projects/${projectId}/files`, form, onProgress);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: fileKeys.list(projectId) }),
  });
}

export function useDeleteFile(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileId: string) => api<null>(`/files/${fileId}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: fileKeys.list(projectId) }),
  });
}
