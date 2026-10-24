/**
 * App-wide reactions to what the fetch wrapper announces (spec §13.4, §13.5 #8):
 * - the session ended (expired or suspended): forget the person's cached data and mark them
 *   signed out, so the route guard sends them to sign in with the reason;
 * - the API answered 503: show the maintenance page, which returns here when it's back.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router";
import { MAINTENANCE_EVENT } from "@/api/client";
import { meKey } from "@/features/auth/api";
import { SIGNED_OUT_EVENT } from "@/lib/sessionNotice";

export const MAINTENANCE_PATH = "/maintenance";

export function AppEvents() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const here = location.pathname + location.search;

  useEffect(() => {
    const onSignedOut = () => {
      qc.removeQueries({
        predicate: (q) => !(q.queryKey.length === meKey.length && q.queryKey[0] === meKey[0]),
      });
      qc.setQueryData(meKey, null);
    };
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    return () => {
      window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
    };
  }, [qc]);

  useEffect(() => {
    const onMaintenance = () => {
      if (location.pathname === MAINTENANCE_PATH) return;
      void navigate(`${MAINTENANCE_PATH}?return_to=${encodeURIComponent(here)}`);
    };
    window.addEventListener(MAINTENANCE_EVENT, onMaintenance);
    return () => {
      window.removeEventListener(MAINTENANCE_EVENT, onMaintenance);
    };
  }, [navigate, here, location.pathname]);

  return null;
}
