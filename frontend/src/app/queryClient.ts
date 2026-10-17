/**
 * Query client with the global error feedback of spec §13.7: 403 → toast and stay, 429 →
 * toast with the wait time. Mutations that show their own inline messages (auth forms)
 * set `meta: { inlineErrors: true }`. 401 is handled by the route guards.
 */
import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast-store";

function waitText(seconds: number | null): string {
  if (!seconds) return "Please wait a moment and try again.";
  if (seconds < 60) return `Try again in ${String(seconds)} seconds.`;
  const minutes = Math.ceil(seconds / 60);
  return `Try again in ${String(minutes)} ${minutes === 1 ? "minute" : "minutes"}.`;
}

export function feedbackFor(error: unknown): void {
  if (!(error instanceof ApiError)) return;
  if (error.status === 403) {
    toast({
      tone: "danger",
      title: "You can’t do that with this account.",
      description: error.message,
    });
  } else if (error.status === 429) {
    toast({ tone: "warning", title: "Too many requests", description: waitText(error.retryAfter) });
  }
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({ onError: feedbackFor }),
    mutationCache: new MutationCache({
      onError: (error, _vars, _ctx, mutation) => {
        if (mutation.meta?.inlineErrors !== true) feedbackFor(error);
      },
    }),
    defaultOptions: {
      queries: { staleTime: 30_000, refetchOnWindowFocus: true, retry: false },
      mutations: { retry: false },
    },
  });
}
