/** Auth and account data hooks. The session lives in an HttpOnly cookie; the
 * browser never sees tokens. `useMe` is the single source of "who am I". */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/api/client";
import type {
  CaptchaChallenge,
  LoginResult,
  Me,
  RecoveryCodes,
  SessionList,
  TotpSetup,
} from "@/api/types";
import { solveChallenge } from "@/lib/captcha";
import { pageLoad } from "@/lib/redirects";
import { clearSessionDrafts } from "@/lib/storage";

export const meKey = ["me"] as const;

/** Re-read the signed-in user now, even while no screen is showing it. After signing in (or a
 * verification that changes the account) the next page's guard must not act on the answer
 * cached before: it held "signed out" and bounced a successful sign-in back to /login. */
export function refreshMe(qc: QueryClient): Promise<void> {
  return qc.invalidateQueries({ queryKey: meKey, refetchType: "all" });
}

/** A new sign-in: drop everything cached for whoever used this tab before (their bids, projects,
 * tests, devices), then read the new user. A session that ended without a page reload (expiry,
 * "sign out everywhere" elsewhere) would otherwise show the old user's data to the next one. */
export async function startSession(qc: QueryClient): Promise<void> {
  qc.removeQueries({
    predicate: (q) => !(q.queryKey.length === meKey.length && q.queryKey[0] === meKey[0]),
  });
  await refreshMe(qc);
}

export function useMe() {
  return useQuery<Me | null>({
    queryKey: meKey,
    staleTime: 30_000,
    retry: false,
    queryFn: async () => {
      try {
        return await api<Me>("/me");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
  });
}

/** Fetch a challenge and solve it (spec §14.16). */
export async function solveCaptcha(signal?: AbortSignal): Promise<string> {
  const challenge = await api<CaptchaChallenge>("/captcha/challenge", signal ? { signal } : {});
  const payload = await solveChallenge(challenge, signal);
  if (!payload) {
    throw new ApiError(
      403,
      {
        error: {
          code: "CAPTCHA_FAILED",
          message: "The automatic bot check didn’t finish. Please try again.",
        },
      },
      null,
    );
  }
  return payload;
}

export interface BotFields {
  captcha?: string | null;
  website: string;
  started_at_ms: number;
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (
      body: { email: string; password: string; return_to?: string | null } & Partial<BotFields>,
    ) => api<LoginResult>("/auth/login", { method: "POST", body }),
    onSuccess: async (result) => {
      if (result.status !== "TOTP_REQUIRED") await startSession(qc);
    },
  });
}

export function useTotpLogin() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: {
      pre_auth: string;
      code?: string;
      recovery_code?: string;
      return_to?: string | null;
    }) => api<LoginResult>("/auth/login/totp", { method: "POST", body }),
    onSuccess: () => startSession(qc),
  });
}

export function useRegister() {
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: Record<string, unknown>) =>
      api<{ message: string }>("/auth/register", { method: "POST", body }),
  });
}

/** Sign out, then load the homepage afresh. A full page load (not an in-app navigation) drops
 * every cached piece of the person's data, and no route guard of the page being left can see
 * "no user" mid-navigation and send them to /login instead (a race WebKit lost, D53). */
export function useLogout(all = false) {
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: () => api<undefined>(all ? "/auth/logout-all" : "/auth/logout", { method: "POST" }),
    onSettled: () => {
      clearSessionDrafts(); // bid drafts and pending leaves belong to this session only
      pageLoad.to("/");
    },
  });
}

/** A new phone code; the bot check is required (spec §14.16). */
export function useSendOtp() {
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: BotFields) => api<undefined>("/auth/otp/send", { method: "POST", body }),
  });
}

export function useVerifyOtp() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (code: string) =>
      api<undefined>("/auth/otp/verify", { method: "POST", body: { code } }),
    onSuccess: () => refreshMe(qc),
  });
}

export function useResendEmail() {
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: BotFields) => api<undefined>("/auth/email/resend", { method: "POST", body }),
  });
}

export function useVerifyEmail() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (token: string) =>
      api<undefined>("/auth/email/verify", { method: "POST", body: { token } }),
    onSuccess: () => refreshMe(qc),
  });
}

export function useForgotPassword() {
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: { email: string } & Partial<BotFields>) =>
      api<{ message: string }>("/auth/password/forgot", { method: "POST", body }),
  });
}

export function useResetPassword() {
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: { token: string; new_password: string }) =>
      api<undefined>("/auth/password/reset", { method: "POST", body }),
  });
}

export function useChangePassword() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api<undefined>("/auth/password/change", { method: "POST", body }),
    // The other devices were signed out: the device list must say so straight away.
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionsKey, refetchType: "all" }),
  });
}

export const sessionsKey = ["sessions"] as const;

export function useSessions() {
  return useQuery({ queryKey: sessionsKey, queryFn: () => api<SessionList>("/auth/sessions") });
}

export function useRevokeSession() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (id: string) =>
      api<undefined>(`/auth/sessions/${encodeURIComponent(id)}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionsKey }),
  });
}

export function useTotpSetup() {
  return useMutation({ mutationFn: () => api<TotpSetup>("/auth/totp/setup", { method: "POST" }) });
}

export function useTotpConfirm() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (code: string) =>
      api<RecoveryCodes>("/auth/totp/confirm", { method: "POST", body: { code } }),
    onSuccess: () => refreshMe(qc),
  });
}

export function useUpdateMe() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: { display_name: string }) => api<Me>("/me", { method: "PATCH", body }),
    onSuccess: (me) => {
      qc.setQueryData(meKey, me);
    },
  });
}
