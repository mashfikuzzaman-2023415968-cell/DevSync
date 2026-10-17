/** Root layout: page titles from route handles ("<Page> · DevSync", spec §13.4), toasts,
 * offline banner, tooltips and scroll restoration for every route. */
import { useEffect } from "react";
import { Outlet, ScrollRestoration, useMatches } from "react-router";
import { OfflineBanner } from "@/components/shell/OfflineBanner";
import { TooltipProvider } from "@/components/ui/Overlay";
import { Toaster } from "@/components/ui/Toaster";

export interface RouteHandle {
  title?: string;
}

export const HOME_TITLE = "DevSync · Plan, hire a fair team, deliver";

export function titleFor(title: string | undefined): string {
  return title ? `${title} · DevSync` : HOME_TITLE;
}

function useRouteTitle() {
  const matches = useMatches();
  const handle = [...matches].reverse().find((m) => (m.handle as RouteHandle | undefined)?.title)
    ?.handle as RouteHandle | undefined;
  useEffect(() => {
    document.title = titleFor(handle?.title);
  }, [handle?.title]);
}

export function Root() {
  useRouteTitle();
  return (
    <TooltipProvider delayDuration={300}>
      <OfflineBanner />
      <Outlet />
      <Toaster />
      <ScrollRestoration />
    </TooltipProvider>
  );
}
