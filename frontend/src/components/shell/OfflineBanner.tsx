/** Offline banner (spec §13.7, §13.5 #8): appears when the browser goes offline or a request
 * fails at the network level, and hides again when a request succeeds. */
import { WifiOff } from "lucide-react";
import { useEffect, useState } from "react";
import { NETWORK_EVENT } from "@/api/client";

export function OfflineBanner() {
  const [offline, setOffline] = useState(
    () => typeof navigator !== "undefined" && !navigator.onLine,
  );
  useEffect(() => {
    const goOffline = () => {
      setOffline(true);
    };
    const goOnline = () => {
      setOffline(false);
    };
    const onNetwork = (e: Event) => {
      setOffline(!(e as CustomEvent<{ online: boolean }>).detail.online);
    };
    window.addEventListener("offline", goOffline);
    window.addEventListener("online", goOnline);
    window.addEventListener(NETWORK_EVENT, onNetwork);
    return () => {
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online", goOnline);
      window.removeEventListener(NETWORK_EVENT, onNetwork);
    };
  }, []);
  if (!offline) return null;
  return (
    <div
      role="status"
      className="fixed inset-x-0 top-0 z-[70] flex items-center justify-center gap-2 bg-text px-4 py-2 pt-[max(env(safe-area-inset-top),8px)] text-body-sm text-bg"
    >
      <WifiOff className="size-4" aria-hidden="true" />
      You’re offline. We’ll keep trying; changes you make now may not be saved.
    </div>
  );
}
