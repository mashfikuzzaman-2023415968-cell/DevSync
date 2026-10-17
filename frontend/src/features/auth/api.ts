/** Auth and account data hooks. The session lives in an HttpOnly cookie; the
 * browser never sees tokens. `useMe` is the single source of "who am I". */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

export const meKey = ["me"] as const;

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
      if (result.status !== "TOTP_REQUIRED") await qc.invalidateQueries({ queryKey: meKey });
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
    onSuccess: () => qc.invalidateQueries({ queryKey: meKey }),
  });
}

export function useRegister() {
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: Record<string, unknown>) =>
      api<{ message: string }>("/auth/register", { method: "POST", body }),
  });
}

/** Sign out. `leave` (e.g. navigate home) runs before the session data is cleared, in the
 * same tick: clearing first would let a route guard send the person to /login and unmount the
 * caller before it could navigate. */
export function useLogout(all = false, leave?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: () => api<undefined>(all ? "/auth/logout-all" : "/auth/logout", { method: "POST" }),
    onSettled: () => {
      leave?.();
      qc.setQueryData(meKey, null);
      qc.clear();
    },
  });
}

export function useSendOtp() {
  return useMutation({ mutationFn: () => api<undefined>("/auth/otp/send", { method: "POST" }) });
}

export function useVerifyOtp() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (code: string) =>
      api<undefined>("/auth/otp/verify", { method: "POST", body: { code } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: meKey }),
  });
}

export function useResendEmail() {
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: () => api<undefined>("/auth/email/resend", { method: "POST" }),
  });
}

export function useVerifyEmail() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (token: string) =>
      api<undefined>("/auth/email/verify", { method: "POST", body: { token } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: meKey }),
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
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api<undefined>("/auth/password/change", { method: "POST", body }),
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
    onSuccess: () => qc.invalidateQueries({ queryKey: meKey }),
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
