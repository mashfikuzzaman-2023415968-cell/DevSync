/** Comment hooks (spec §10.2, §13.7; D146): a conversation oldest first, posting optimistically
 * (the comment shows at once and is taken back with the reason if refused), editing within 15
 * minutes and deleting your own. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { CommentItem, CommentPage, PersonRef } from "@/api/types";

export type CommentTargetType = "TASK" | "MILESTONE" | "CHECKIN";

export const commentKeys = {
  thread: (type: CommentTargetType, id: string) => ["comments", type, id] as const,
};

export function useComments(type: CommentTargetType, id: string) {
  return useQuery({
    queryKey: commentKeys.thread(type, id),
    queryFn: () =>
      api<CommentPage>(`/comments?target_type=${type}&target_id=${encodeURIComponent(id)}&limit=100`),
    staleTime: 30_000,
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
    mutationFn: (c: NewComment) =>
      api<CommentItem>("/comments", {
        method: "POST",
        body: {
          target_type: type,
          target_id: id,
          body: c.body,
          mention_ids: c.mentions.map((m) => m.id),
          reply_to_id: c.replyToId,
        },
      }),
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
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}

export function useEditComment(type: CommentTargetType, id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({ comment, body }: { comment: CommentItem; body: string }) =>
      api<CommentItem>(`/comments/${comment.id}`, {
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
      api<null>(`/comments/${comment.id}`, {
        method: "DELETE",
        headers: { "If-Match": String(comment.version) },
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: commentKeys.thread(type, id) }),
  });
}
