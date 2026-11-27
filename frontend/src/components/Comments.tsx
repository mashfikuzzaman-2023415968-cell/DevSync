/**
 * A comment thread (spec §13.5 #30 task drawer, #34 blocker replies; §13.7; D146).
 *
 * Plain text rendered as text; only https links become links (`linkify`, with
 * `rel="noopener noreferrer nofollow"`). Mentions are picked from the team list, never parsed out
 * of the text. Authors edit within 15 minutes ("edited" shows) and delete their own; a deleted
 * comment keeps its place without its text. Posting is optimistic and rolls back with the reason.
 * Read-only viewers (admins, finished projects) see the thread without the composer.
 */
import { AtSign, Reply, X } from "lucide-react";
import { useState } from "react";
import { ApiError } from "@/api/client";
import type { CommentItem, PersonRef } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Avatar, Skeleton } from "@/components/ui/Display";
import { Alert, ErrorState } from "@/components/ui/Feedback";
import { Textarea } from "@/components/ui/Field";
import { ConfirmDialog } from "@/components/ui/Overlay";
import { Select } from "@/components/ui/Select";
import { toast } from "@/components/ui/toast-store";
import { messageFor } from "@/features/auth/errors";
import {
  useComments,
  useDeleteComment,
  useEditComment,
  usePostComment,
  type CommentTargetType,
} from "@/features/workspace/commentsApi";
import { formatDateTime, formatRelative } from "@/lib/format";
import { linkify } from "@/lib/linkify";

const MAX_BODY = 4000;
const MAX_MENTIONS = 10;

export function CommentText({ text }: { text: string }) {
  return (
    <p className="whitespace-pre-wrap break-words text-body-sm text-text">
      {linkify(text).map((s, i) =>
        s.kind === "link" ? (
          <a
            key={`${String(i)}-${s.href}`}
            href={s.href}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="break-all text-primary underline"
          >
            {s.value}
          </a>
        ) : (
          <span key={`${String(i)}-t`}>{s.value}</span>
        ),
      )}
    </p>
  );
}

interface Props {
  targetType: CommentTargetType;
  targetId: string;
  /** People who can be mentioned (the team). */
  people: PersonRef[];
  me: PersonRef | null;
  canWrite: boolean;
  label?: string;
}

export function Comments({ targetType, targetId, people, me, canWrite, label = "Comments" }: Props) {
  const q = useComments(targetType, targetId);
  const post = usePostComment(targetType, targetId);
  const [body, setBody] = useState("");
  const [mentions, setMentions] = useState<PersonRef[]>([]);
  const [replyTo, setReplyTo] = useState<CommentItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const items = q.data?.items ?? [];
  const byId = new Map(items.map((c) => [c.id, c]));

  const send = () => {
    const text = body.trim();
    if (!text || !me) return;
    setError(null);
    post.mutate(
      { body: text, mentions, replyToId: replyTo?.id ?? null, author: me },
      {
        onSuccess: () => {
          setBody("");
          setMentions([]);
          setReplyTo(null);
        },
        onError: (e) => {
          setError(messageFor(e));
        },
      },
    );
  };

  return (
    <section aria-label={label} className="space-y-3">
      <h3 className="text-body-sm font-semibold">{label}</h3>
      {q.isPending ? (
        <Skeleton className="h-16 w-full" />
      ) : q.isError ? (
        <ErrorState
          title="Comments didn’t load"
          requestId={q.error instanceof ApiError ? q.error.requestId : null}
          onRetry={() => void q.refetch()}
        />
      ) : items.length === 0 ? (
        <p className="text-body-sm text-text-muted">No comments yet.</p>
      ) : (
        <ul className="space-y-3">
          {items.map((c) => (
            <CommentRow
              key={c.id}
              comment={c}
              parent={c.reply_to_id ? byId.get(c.reply_to_id) : undefined}
              targetType={targetType}
              targetId={targetId}
              canReply={canWrite}
              mine={canWrite && me !== null && c.author.id === me.id}
              onReply={() => {
                setReplyTo(c);
              }}
            />
          ))}
        </ul>
      )}
      {canWrite && me ? (
        <div className="sticky bottom-0 space-y-2 border-t border-border bg-surface pt-3">
          {error ? <Alert tone="danger">{error}</Alert> : null}
          {replyTo ? (
            <p className="flex items-center gap-2 text-caption text-text-muted">
              Replying to {replyTo.author.name}
              <Button
                variant="ghost"
                size="sm"
                aria-label="Stop replying"
                onClick={() => {
                  setReplyTo(null);
                }}
              >
                <X className="size-4" aria-hidden="true" />
              </Button>
            </p>
          ) : null}
          <Textarea
            aria-label="Write a comment"
            rows={2}
            maxLength={MAX_BODY}
            value={body}
            onChange={(e) => {
              setBody(e.target.value);
            }}
          />
          <div className="flex flex-wrap items-center gap-2">
            {mentions.map((m) => (
              <span
                key={m.id}
                className="inline-flex items-center gap-1 rounded-full bg-primary-soft px-2 py-0.5 text-caption text-primary"
              >
                @{m.name}
                <button
                  type="button"
                  aria-label={`Don’t mention ${m.name}`}
                  className="inline-flex size-6 items-center justify-center"
                  onClick={() => {
                    setMentions((all) => all.filter((x) => x.id !== m.id));
                  }}
                >
                  <X className="size-3.5" aria-hidden="true" />
                </button>
              </span>
            ))}
            {mentions.length < MAX_MENTIONS ? (
              <div className="w-48">
                <Select
                  aria-label="Mention someone"
                  value={undefined}
                  placeholder="Mention…"
                  onChange={(id) => {
                    const person = people.find((p) => p.id === id);
                    if (person && !mentions.some((m) => m.id === id))
                      setMentions((all) => [...all, person]);
                  }}
                  options={people
                    .filter((p) => p.id !== me.id && !mentions.some((m) => m.id === p.id))
                    .map((p) => ({ value: p.id, label: p.name }))}
                />
              </div>
            ) : null}
            <Button
              className="ml-auto"
              disabled={!body.trim()}
              loading={post.isPending}
              onClick={send}
            >
              <AtSign className="size-4" aria-hidden="true" /> Post comment
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function CommentRow({
  comment,
  parent,
  targetType,
  targetId,
  canReply,
  mine,
  onReply,
}: {
  comment: CommentItem;
  parent: CommentItem | undefined;
  targetType: CommentTargetType;
  targetId: string;
  canReply: boolean;
  /** The viewer wrote it (they may delete it at any time; edit only within 15 minutes). */
  mine: boolean;
  onReply: () => void;
}) {
  const edit = useEditComment(targetType, targetId);
  const remove = useDeleteComment(targetType, targetId);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(comment.body);
  return (
    <li className="flex gap-3">
      <Avatar name={comment.author.name} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-baseline gap-x-2 text-caption text-text-muted">
          <span className="text-body-sm font-medium text-text">{comment.author.name}</span>
          <time dateTime={comment.created_at} title={formatDateTime(comment.created_at)} data-volatile>
            {formatRelative(comment.created_at)}
          </time>
          {comment.edited && !comment.deleted ? <span>edited</span> : null}
        </p>
        {parent ? (
          <p className="text-caption text-text-muted">Replying to {parent.author.name}</p>
        ) : null}
        {comment.deleted ? (
          <p className="text-body-sm italic text-text-muted">Comment deleted</p>
        ) : editing ? (
          <div className="mt-1 space-y-2">
            <Textarea
              aria-label="Edit your comment"
              rows={2}
              maxLength={MAX_BODY}
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
              }}
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                loading={edit.isPending}
                disabled={!draft.trim()}
                onClick={() => {
                  edit.mutate(
                    { comment, body: draft.trim() },
                    {
                      onSuccess: () => {
                        setEditing(false);
                      },
                      onError: (e) => {
                        toast({ tone: "danger", title: messageFor(e) });
                      },
                    },
                  );
                }}
              >
                Save
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditing(false);
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <CommentText text={comment.body} />
        )}
        {!comment.deleted && comment.mentions.length > 0 ? (
          <p className="text-caption text-text-muted">
            Mentioned {comment.mentions.map((m) => m.name).join(", ")}
          </p>
        ) : null}
        {!comment.deleted ? (
          <div className="mt-1 flex gap-1">
            {canReply ? (
              <Button size="sm" variant="ghost" onClick={onReply}>
                <Reply className="size-4" aria-hidden="true" /> Reply
              </Button>
            ) : null}
            {comment.can_edit && !editing ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setDraft(comment.body);
                  setEditing(true);
                }}
              >
                Edit
              </Button>
            ) : null}
            {mine ? (
              <ConfirmDialog
                trigger={
                  <Button size="sm" variant="ghost">
                    Delete
                  </Button>
                }
                title="Delete this comment?"
                description="Its text disappears for everyone; the conversation keeps its place."
                confirmLabel="Delete comment"
                onConfirm={async () => {
                  try {
                    await remove.mutateAsync(comment);
                  } catch (e) {
                    toast({ tone: "danger", title: messageFor(e) });
                  }
                }}
              />
            ) : null}
          </div>
        ) : null}
      </div>
    </li>
  );
}
