/** Comment hooks (spec §10.2, §13.7; D146): a conversation oldest first, posting optimistically
 * (the comment shows at once and is taken back with the reason if refused), editing within 15
 * minutes and deleting your own. A discussion thread is the same kind of conversation: its target
 * type is `DISCUSSION_POST` and its id is the thread's; only the addresses differ, and it is
 * polled every 15 s while the page is visible. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { CommentItem, CommentPage, PersonRef } from "@/api/types";

export type CommentTargetType = "TASK" | "MILESTONE" | "CHECKIN" | "DISCUSSION_POST";

/** D146: discussion threads refresh every 15 s while visible (TanStack pauses hidden tabs). */
export const DISCUSSION_POLL_MS = 15_000;

export const commentKeys = {
  thread: (type: CommentTargetType, id: string) => ["comments", type, id] as const,
};

const isPost = (type: CommentTargetType) => type === "DISCUSSION_POST";

function listPath(type: CommentTargetType, id: string): string {
  const target = encodeURIComponent(id);
  return isPost(type)
    ? `/threads/${target}/posts?limit=100`
    : `/comments?target_type=${type}&target_id=${target}&limit=100`;
}

function itemPath(type: CommentTargetType, itemId: string): string {
  return isPost(type) ? `/posts/${itemId}` : `/comments/${itemId}`;
}

export function useComments(type: CommentTargetType, id: string) {
  return useQuery({
    queryKey: commentKeys.thread(type, id),
    queryFn: () => api<CommentPage>(listPath(type, id)),
    staleTime: isPost(type) ? 0 : 30_000,
    refetchInterval: isPost(type) ? DISCUSSION_POLL_MS : false,
  });
}

export interface NewComment {
  body: string;
  mentions: PersonRef[];
  replyToId: string | null;
  author: PersonRef;
}

export function usePostComment(type: CommentTargetType, id: string) {
  const qc = useQueryClient();
  const key = commentKeys.thread(type, id);
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (c: NewComment) => {
      const common = {
        body: c.body,
        mention_ids: c.mentions.map((m) => m.id),
        reply_to_id: c.replyToId,
      };
      return isPost(type)
        ? api<CommentItem>(`/threads/${id}/posts`, { method: "POST", body: common })
        : api<CommentItem>("/comments", {
            method: "POST",
            body: { target_type: type, target_id: id, ...common },
          });
    },
    onMutate: async (c) => {
      await qc.cancelQueries({ queryKey: key });
      const before = qc.getQueryData<CommentPage>(key);
      const draft: CommentItem = {
        id: `pending-${String(Date.now())}`,
        target_type: type,
        target_id: id,
        author: c.author,
        body: c.body,
        mentions: c.mentions,
        reply_to_id: c.replyToId,
        created_at: new Date().toISOString(),
        edited: false,
        deleted: false,
        can_edit: false,
        version: 0,
      };
      qc.setQueryData<CommentPage>(key, (d) => (d ? { ...d, items: [...d.items, draft] } : d));
      return { before };
    },
    onError: (_e, _c, ctx) => {
      if (ctx) qc.setQueryData(key, ctx.before);
    },
    onSettled: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: key }),
        // A new post floats its thread to the top of the list.
        isPost(type) ? qc.invalidateQueries({ queryKey: ["threads"] }) : Promise.resolve(),
      ]),
  });
}

export function useEditComment(type: CommentTargetType, id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({ comment, body }: { comment: CommentItem; body: string }) =>
      api<CommentItem>(itemPath(type, comment.id), {
        method: "PATCH",
        body: { body },
        headers: { "If-Match": String(comment.version) },
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: commentKeys.thread(type, id) }),
  });
}

export function useDeleteComment(type: CommentTargetType, id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (comment: CommentItem) =>
      api<null>(itemPath(type, comment.id), {
        method: "DELETE",
        headers: { "If-Match": String(comment.version) },
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: commentKeys.thread(type, id) }),
  });
}
