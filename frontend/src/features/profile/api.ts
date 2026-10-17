/** Profile, portfolio, evidence and skill-test data hooks (spec §10.2 Profiles, Tests). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, upload } from "@/api/client";
import type {
  AnswerAccepted,
  Attempt,
  AttemptResult,
  Certificate,
  ClientProfile,
  ClientProfileUpdate,
  DeveloperProfile,
  DeveloperProfileUpdate,
  DeveloperSkill,
  ExternalReview,
  PortfolioItem,
  PortfolioItemCreate,
  PortfolioItemUpdate,
  PublicProfile,
  Skill,
  SkillTest,
} from "@/api/types";

export const keys = {
  skills: ["skills"] as const,
  profile: ["me", "developer-profile"] as const,
  client: ["me", "client-profile"] as const,
  portfolio: ["me", "portfolio"] as const,
  certificates: ["me", "certificates"] as const,
  reviews: ["me", "external-reviews"] as const,
  tests: ["skill-tests"] as const,
  attempt: (id: string) => ["attempts", id] as const,
  developer: (id: string) => ["developers", id] as const,
};

export function useSkills() {
  return useQuery({
    queryKey: keys.skills,
    staleTime: 10 * 60_000,
    queryFn: () => api<Skill[]>("/skills"),
  });
}

export function useDeveloperProfile() {
  return useQuery({
    queryKey: keys.profile,
    queryFn: () => api<DeveloperProfile>("/me/developer-profile"),
  });
}

export function useUpdateDeveloperProfile() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: DeveloperProfileUpdate) =>
      api<DeveloperProfile>("/me/developer-profile", { method: "PATCH", body }),
    onSuccess: (data) => {
      qc.setQueryData(keys.profile, data);
    },
  });
}

export function useReplaceSkills() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (skills: { skill_id: string; self_level: number }[]) =>
      api<DeveloperSkill[]>("/me/skills", { method: "PUT", body: { skills } }),
    onSuccess: (skills) => {
      qc.setQueryData<DeveloperProfile>(keys.profile, (old) => (old ? { ...old, skills } : old));
    },
  });
}

export function useClientProfile() {
  return useQuery({
    queryKey: keys.client,
    queryFn: () => api<ClientProfile>("/me/client-profile"),
  });
}

export function useUpdateClientProfile() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: ClientProfileUpdate) =>
      api<ClientProfile>("/me/client-profile", { method: "PATCH", body }),
    onSuccess: (data) => {
      qc.setQueryData(keys.client, data);
    },
  });
}

// ---------------------------------------------------------------- portfolio

export function usePortfolio() {
  return useQuery({
    queryKey: keys.portfolio,
    queryFn: () => api<PortfolioItem[]>("/me/portfolio"),
  });
}

function usePortfolioMutation<V>(
  fn: (vars: V) => Promise<PortfolioItem | PortfolioItem[] | undefined>,
) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: fn,
    onSettled: () => qc.invalidateQueries({ queryKey: keys.portfolio }),
  });
}

export function useCreatePortfolioItem() {
  return usePortfolioMutation((body: PortfolioItemCreate) =>
    api<PortfolioItem>("/me/portfolio", { method: "POST", body }),
  );
}

export function useUpdatePortfolioItem() {
  return usePortfolioMutation(({ id, body }: { id: string; body: PortfolioItemUpdate }) =>
    api<PortfolioItem>(`/me/portfolio/${id}`, { method: "PATCH", body }),
  );
}

export function useDeletePortfolioItem() {
  return usePortfolioMutation((id: string) =>
    api<undefined>(`/me/portfolio/${id}`, { method: "DELETE" }),
  );
}

export function useReorderPortfolio() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (ids: string[]) =>
      api<PortfolioItem[]>("/me/portfolio-order", { method: "PUT", body: { ids } }),
    // Optimistic: the list moves at once; a failure restores the server order.
    onMutate: async (ids) => {
      await qc.cancelQueries({ queryKey: keys.portfolio });
      const before = qc.getQueryData<PortfolioItem[]>(keys.portfolio);
      if (before) {
        const byId = new Map(before.map((i) => [i.id, i]));
        qc.setQueryData(
          keys.portfolio,
          ids.flatMap((id, position) => {
            const item = byId.get(id);
            return item ? [{ ...item, position }] : [];
          }),
        );
      }
      return { before };
    },
    onError: (_e, _ids, ctx) => {
      if (ctx?.before) qc.setQueryData(keys.portfolio, ctx.before);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: keys.portfolio }),
  });
}

export function uploadPortfolioImage(
  itemId: string,
  file: File,
  onProgress: (fraction: number) => void,
) {
  const form = new FormData();
  form.append("file", file);
  return upload<PortfolioItem>(`/me/portfolio/${itemId}/images`, form, onProgress);
}

export function useDeletePortfolioImage() {
  return usePortfolioMutation(({ itemId, imageId }: { itemId: string; imageId: string }) =>
    api<PortfolioItem>(`/me/portfolio/${itemId}/images/${imageId}`, { method: "DELETE" }),
  );
}

// ---------------------------------------------------------------- evidence

export function useCertificates() {
  return useQuery({
    queryKey: keys.certificates,
    queryFn: () => api<Certificate[]>("/me/certificates"),
  });
}

export function uploadCertificate(
  fields: { title: string; issuer: string },
  file: File,
  onProgress: (fraction: number) => void,
) {
  const form = new FormData();
  form.append("title", fields.title);
  form.append("issuer", fields.issuer);
  form.append("file", file);
  return upload<Certificate>("/me/certificates", form, onProgress);
}

export function useDeleteCertificate() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (id: string) => api<undefined>(`/me/certificates/${id}`, { method: "DELETE" }),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.certificates }),
  });
}

export function useExternalReviews() {
  return useQuery({
    queryKey: keys.reviews,
    queryFn: () => api<ExternalReview[]>("/me/external-reviews"),
  });
}

export interface ReviewFields {
  source: string;
  rating: string;
  scale: string;
  project_date: string;
}

export function uploadExternalReview(
  fields: ReviewFields,
  file: File,
  onProgress: (fraction: number) => void,
) {
  const form = new FormData();
  form.append("source", fields.source);
  form.append("rating", fields.rating);
  form.append("scale", fields.scale);
  form.append("project_date", fields.project_date);
  form.append("file", file);
  return upload<ExternalReview>("/me/external-reviews", form, onProgress);
}

export function useDeleteExternalReview() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (id: string) => api<undefined>(`/me/external-reviews/${id}`, { method: "DELETE" }),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.reviews }),
  });
}

// ---------------------------------------------------------------- viewing developers

/** A developer's profile: the signed-in view when there is a session, else the public one. */
export function useDeveloper(id: string, signedIn: boolean) {
  return useQuery({
    queryKey: [...keys.developer(id), signedIn],
    retry: false,
    queryFn: () => api<PublicProfile>(signedIn ? `/developers/${id}` : `/public/developers/${id}`),
  });
}

// ---------------------------------------------------------------- skill tests

export function useSkillTests() {
  return useQuery({ queryKey: keys.tests, queryFn: () => api<SkillTest[]>("/skill-tests") });
}

export function useStartAttempt() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (testId: string) =>
      api<Attempt>(`/skill-tests/${testId}/attempts`, { method: "POST" }),
    onSuccess: (attempt) => {
      qc.setQueryData(keys.attempt(attempt.id), attempt);
      void qc.invalidateQueries({ queryKey: keys.tests });
    },
  });
}

export function useAttempt(id: string) {
  return useQuery({
    queryKey: keys.attempt(id),
    retry: false,
    staleTime: Infinity,
    queryFn: () => api<Attempt>(`/attempts/${id}`),
  });
}

export function useAnswer(attemptId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: { question_id: string; choice: number }) =>
      api<AnswerAccepted>(`/attempts/${attemptId}/answer`, { method: "POST", body }),
    onSuccess: (_r, body) => {
      qc.setQueryData<Attempt>(keys.attempt(attemptId), (old) =>
        old ? { ...old, answers: { ...old.answers, [body.question_id]: body.choice } } : old,
      );
    },
  });
}

export function useSubmitAttempt(attemptId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: () => api<AttemptResult>(`/attempts/${attemptId}/submit`, { method: "POST" }),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.tests });
      void qc.invalidateQueries({ queryKey: keys.attempt(attemptId) });
    },
  });
}
