/**
 * The bid sheet's draft, kept while a newcomer takes the role assessment (role assessment spec
 * §11.2, Decision 13): in memory, and in sessionStorage under `devsync:bid-draft:{project}` so a
 * reload of the tab keeps it. Only non-sensitive fields; cleared when the bid is placed and on
 * sign-out.
 */
import { useCallback, useEffect, useState } from "react";
import { readSession, writeSession } from "@/lib/storage";

export interface BidDraft {
  slotId: string;
  priceTaka: string;
  days: string;
  hours: string;
  proposal: string;
}

const EMPTY: BidDraft = { slotId: "", priceTaka: "", days: "", hours: "", proposal: "" };

export function bidDraftKey(projectId: string): string {
  return `devsync:bid-draft:${projectId}`;
}

export function useBidDraft(projectId: string) {
  const key = bidDraftKey(projectId);
  const [draft, setDraft] = useState<BidDraft>(() => ({
    ...EMPTY,
    ...readSession<Partial<BidDraft>>(key, {}),
  }));

  useEffect(() => {
    const empty = Object.values(draft).every((v) => v === "");
    writeSession(key, empty ? null : draft);
  }, [draft, key]);

  const update = useCallback((patch: Partial<BidDraft>) => {
    setDraft((d) => ({ ...d, ...patch }));
  }, []);
  const clear = useCallback(() => {
    writeSession(key, null);
    setDraft(EMPTY);
  }, [key]);
  return { draft, update, clear };
}
