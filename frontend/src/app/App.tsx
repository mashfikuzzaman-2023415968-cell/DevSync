import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider } from "react-router";
import { PreferencesProvider } from "@/design/preferences";
import { createQueryClient } from "./queryClient";
import { router } from "./router";

/** Providers + router. Server state lives in TanStack Query (spec §13.7); theme and motion
 * preferences wrap everything (§13.1–13.2). */
export function App({ nonce }: { nonce?: string | undefined }) {
  const [client] = useState(createQueryClient);
  return (
    <QueryClientProvider client={client}>
      <PreferencesProvider nonce={nonce}>
        <RouterProvider router={router} />
      </PreferencesProvider>
    </QueryClientProvider>
  );
}
