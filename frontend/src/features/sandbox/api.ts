/** The developer SMS inbox (OTP sandbox): texts DevSync "sent" in development, tests and the
 * offline demo stack. The routes do not exist anywhere else, so a 404 means "off here". */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/api/client";

export interface SandboxSms {
  id: string;
  to: string;
  text: string;
  code: string | null;
  at: string;
}

export interface SandboxSmsList {
  messages: SandboxSms[];
  newest_code: string | null;
}

export const smsInboxKey = ["sandbox", "sms"] as const;

/** How often a live inbox looks for new texts. */
export const INBOX_POLL_MS = 3000;

export function useSmsInbox(live: boolean) {
  return useQuery<SandboxSmsList, ApiError>({
    queryKey: smsInboxKey,
    queryFn: () => api<SandboxSmsList>("/dev-sandbox/sms?limit=100"),
    refetchInterval: live ? INBOX_POLL_MS : false,
    // "Off here" (404) is an answer, not a glitch worth retrying.
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 1,
  });
}

export function useClearSmsInbox() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<undefined>("/dev-sandbox/sms", { method: "DELETE" }),
    meta: { inlineErrors: true },
    onSuccess: () => qc.invalidateQueries({ queryKey: smsInboxKey }),
  });
}

/** Keep only the digits, so "+880 1712-345678" finds "+8801712345678". */
export function digitsOnly(value: string): string {
  return value.replace(/[^0-9]/g, "");
}
