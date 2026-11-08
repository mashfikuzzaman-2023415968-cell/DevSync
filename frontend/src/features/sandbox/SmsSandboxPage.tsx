/** Developer SMS inbox (OTP sandbox): where the phone code of a sign-up shows up in a demo or
 * while developing, instead of on a phone. Public on purpose (the first code is read before an
 * account exists); the server only mounts it in development, tests and the offline demo stack. */
import { Check, Copy, ExternalLink, MailOpen, Radio, Smartphone, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import { Wordmark } from "@/components/brand/Logo";
import { Button } from "@/components/ui/Button";
import { Switch } from "@/components/ui/Choice";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Field";
import { toast } from "@/components/ui/toast-store";
import { formatRelative } from "@/lib/format";
import { digitsOnly, useClearSmsInbox, useSmsInbox, type SandboxSms } from "./api";

/** Mailpit, the local mail catcher every development and demo stack already runs. */
const MAIL_INBOX_URL = "http://127.0.0.1:8025";

async function copyCode(code: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(code);
    toast({ tone: "success", title: "Code copied", description: code });
  } catch {
    toast({ tone: "warning", title: "Couldn’t copy", description: "Select the code and copy it." });
  }
}

/** Re-renders every `ms` so "12 seconds ago" keeps counting between refreshes. */
function useNow(ms: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => {
      setNow(new Date());
    }, ms);
    return () => {
      window.clearInterval(id);
    };
  }, [ms]);
  return now;
}

function CopyButton({ code, size = "sm" }: { code: string; size?: "sm" | "md" }) {
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (!done) return;
    const id = window.setTimeout(() => {
      setDone(false);
    }, 1500);
    return () => {
      window.clearTimeout(id);
    };
  }, [done]);
  return (
    <Button
      variant="outline"
      size={size}
      icon={done ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
      onClick={() => {
        void copyCode(code);
        setDone(true);
      }}
      aria-label={`Copy code ${code}`}
    >
      {done ? "Copied" : "Copy"}
    </Button>
  );
}

function NewestCode({ message, now }: { message: SandboxSms; now: Date }) {
  return (
    <Card className="border-primary/30 bg-primary-soft">
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0" aria-live="polite">
          <p className="text-body-sm text-text-muted">
            Newest code, sent to <span className="font-mono text-text">{message.to}</span>{" "}
            <span title={new Date(message.at).toLocaleString("en-GB", { timeZone: "Asia/Dhaka" })}>
              {formatRelative(message.at, now)}
            </span>
          </p>
          <p
            className="mt-1 font-mono text-hero font-semibold tracking-[0.2em] text-text"
            data-testid="newest-code"
          >
            {message.code}
          </p>
        </div>
        <CopyButton code={message.code ?? ""} size="md" />
      </div>
    </Card>
  );
}

function MessageRow({ message, now }: { message: SandboxSms; now: Date }) {
  return (
    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-body-sm">
          <span className="font-mono font-medium text-text">{message.to}</span>
          <span
            className="text-caption text-text-muted"
            title={new Date(message.at).toLocaleString("en-GB", { timeZone: "Asia/Dhaka" })}
          >
            {formatRelative(message.at, now)}
          </span>
        </p>
        <p className="mt-1 break-words text-body-sm text-text-muted">{message.text}</p>
      </div>
      {message.code ? (
        <div className="flex shrink-0 items-center gap-3">
          <Badge tone="primary">
            <span className="font-mono tracking-widest">{message.code}</span>
          </Badge>
          <CopyButton code={message.code} />
        </div>
      ) : null}
    </li>
  );
}

export default function SmsSandboxPage() {
  const [live, setLive] = useState(true);
  const [filter, setFilter] = useState("");
  const inbox = useSmsInbox(live);
  const clear = useClearSmsInbox();
  const now = useNow(5000);

  const wanted = digitsOnly(filter);
  const shown = useMemo(
    () =>
      (inbox.data?.messages ?? []).filter(
        (m) => wanted === "" || digitsOnly(m.to).includes(wanted),
      ),
    [inbox.data, wanted],
  );
  const newest = shown.find((m) => m.code);
  const off = inbox.error instanceof ApiError && inbox.error.status === 404;

  return (
    <div className="min-h-dvh bg-bg">
      <header className="mx-auto flex max-w-content items-center justify-between px-4 py-5 sm:px-6">
        <Link
          to="/"
          className="inline-flex min-h-11 items-center rounded-md"
          aria-label="DevSync home"
        >
          <Wordmark />
        </Link>
        <Badge tone="warning">Developer sandbox</Badge>
      </header>
      <main id="main" className="mx-auto max-w-3xl px-4 pb-24 pt-4 sm:px-6">
        <PageHeader
          title="SMS inbox"
          description="The texts DevSync sent here. Nothing reaches a real phone."
          action={
            <Button
              variant="outline"
              icon={<Trash2 aria-hidden="true" />}
              loading={clear.isPending}
              disabled={off || (inbox.data?.messages.length ?? 0) === 0}
              onClick={() => {
                clear.mutate(undefined, {
                  onSuccess: () => toast({ tone: "success", title: "Inbox cleared" }),
                  onError: () =>
                    toast({
                      tone: "danger",
                      title: "Couldn’t clear the inbox",
                      description: "Try again.",
                    }),
                });
              }}
            >
              Clear inbox
            </Button>
          }
        />

        {off ? (
          <Card>
            <EmptyState
              icon={<Smartphone aria-hidden="true" />}
              title="The SMS inbox is off here"
              description="It only runs in development, in tests and on the offline demo stack, so real deployments never expose codes."
            />
          </Card>
        ) : inbox.isError ? (
          <Card>
            <ErrorState
              title="The inbox didn’t load"
              requestId={inbox.error instanceof ApiError ? inbox.error.requestId : null}
              onRetry={() => void inbox.refetch()}
            />
          </Card>
        ) : (
          <div className="space-y-6">
            <Card>
              <div className="grid gap-2 p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-6">
                <div>
                  <label htmlFor="sms-filter" className="text-body-sm font-medium text-text">
                    Show texts to
                  </label>
                  <Input
                    id="sms-filter"
                    type="search"
                    inputMode="tel"
                    autoComplete="off"
                    placeholder="Any number, for example +880 17"
                    value={filter}
                    onChange={(e) => {
                      setFilter(e.target.value);
                    }}
                    className="mt-1"
                  />
                </div>
                <Switch
                  label="Refresh every few seconds"
                  checked={live}
                  onCheckedChange={setLive}
                />
              </div>
            </Card>

            {inbox.isPending ? (
              <div className="space-y-3" aria-busy="true" aria-label="Loading texts">
                <Skeleton className="h-24 w-full" />
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : (
              <>
                {newest ? <NewestCode message={newest} now={now} /> : null}
                <Card>
                  <CardHeader
                    title="Texts"
                    description={
                      shown.length === 0
                        ? undefined
                        : `${String(shown.length)} ${shown.length === 1 ? "text" : "texts"}, newest first`
                    }
                    action={
                      live ? (
                        <span className="inline-flex items-center gap-1.5 text-caption text-text-muted">
                          <Radio className="size-4 text-success" aria-hidden="true" /> Live
                        </span>
                      ) : null
                    }
                  />
                  {shown.length === 0 ? (
                    <EmptyState
                      icon={<Smartphone aria-hidden="true" />}
                      title={wanted === "" ? "No texts yet" : "No texts to that number"}
                      description={
                        wanted === ""
                          ? "Create an account or ask for a new code on the verify page. The text appears here within a few seconds."
                          : "Clear the number above to see every text."
                      }
                    />
                  ) : (
                    <ul className="divide-y divide-border">
                      {shown.map((m) => (
                        <MessageRow key={m.id} message={m} now={now} />
                      ))}
                    </ul>
                  )}
                </Card>
              </>
            )}

            <p className="flex flex-wrap items-center gap-x-2 text-body-sm text-text-muted">
              <MailOpen className="size-4" aria-hidden="true" />
              Looking for an email instead?
              <a
                href={MAIL_INBOX_URL}
                rel="noopener noreferrer"
                target="_blank" // forbidden-ok: rel="noopener noreferrer" is set on the line above
                className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
              >
                Open the mail inbox <ExternalLink className="size-3.5" aria-hidden="true" />
              </a>
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
