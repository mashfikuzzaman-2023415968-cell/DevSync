import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { PreferencesProvider } from "@/design/preferences";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import { AudienceToggle } from "./Audience";
import { FAQ, Faq } from "./Faq";
import { FairnessSpotlight } from "./FairnessSpotlight";
import { heroFallbackReason, webglIsSoftware, whenIdle } from "./heroSupport";
import { HEADLINE } from "./Hero";
import LandingPage from "./LandingPage";
import { StatsStrip } from "./StatsStrip";

function landing(stats: Record<string, unknown> = {}) {
  server.use(
    http.get("*/api/v1/me", () =>
      HttpResponse.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 }),
    ),
    http.get("*/api/v1/public/stats", () => HttpResponse.json(stats)),
  );
  return renderRoutes([{ path: "/", element: <LandingPage /> }], "/");
}

describe("homepage (spec §13.11)", () => {
  it("has one h1 with the full headline and every section", async () => {
    landing();
    expect(await screen.findByRole("heading", { level: 1, name: HEADLINE })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    for (const id of ["how-it-works", "features", "fairness", "research", "faq"]) {
      expect(document.getElementById(id)).not.toBeNull();
    }
    expect(screen.getByText(/Illustration: many developers/)).toHaveClass("sr-only");
  });

  it("navbar and footer reach every public path", async () => {
    landing();
    const header = await screen.findByRole("navigation", { name: "Main" });
    expect(within(header).getByRole("link", { name: "Browse projects" })).toHaveAttribute(
      "href",
      "/projects",
    );
    expect(screen.getAllByRole("link", { name: "Get started" })[0]).toHaveAttribute(
      "href",
      "/register",
    );
    expect(screen.getAllByRole("link", { name: "Sign in" })[0]).toHaveAttribute("href", "/login");
    const footer = screen.getByRole("navigation", { name: "Footer" });
    expect(within(footer).getByRole("link", { name: "Privacy" })).toHaveAttribute(
      "href",
      "/privacy",
    );
    expect(within(footer).getByRole("link", { name: "Terms of use" })).toHaveAttribute(
      "href",
      "/terms",
    );
  });
});

describe("StatsStrip", () => {
  it("shows the research line only, never zeros, when there are no numbers", async () => {
    server.use(http.get("*/api/v1/public/stats", () => HttpResponse.json({ developers: 0 })));
    renderRoutes([{ path: "/", element: <StatsStrip /> }], "/");
    expect(
      await screen.findByText(/published research from the University of Dhaka/),
    ).toBeInTheDocument();
    expect(screen.queryByText("developers")).not.toBeInTheDocument();
  });

  it("shows live numbers when they exist", async () => {
    server.use(http.get("*/api/v1/public/stats", () => HttpResponse.json({ developers: 1240 })));
    renderRoutes([{ path: "/", element: <StatsStrip /> }], "/");
    expect(await screen.findByText("developers")).toBeInTheDocument();
    expect(screen.getByText("1.2k", { selector: ".sr-only" })).toBeInTheDocument();
  });
});

describe("interactive sections", () => {
  it("switches benefit lists for clients and developers", async () => {
    const user = userEvent.setup();
    renderRoutes([{ path: "/", element: <AudienceToggle /> }], "/");
    expect(screen.getByText("Plan in minutes")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "For developers" }));
    expect(await screen.findByText("A fair first chance")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Find work" })).toHaveAttribute(
      "href",
      "/register?role=developer",
    );
  });

  it("fairness dial changes the kept places and shows no invented numbers (D21)", async () => {
    const user = userEvent.setup();
    render(
      <PreferencesProvider>
        <FairnessSpotlight />
      </PreferencesProvider>,
    );
    expect(screen.getByText("1 of 4 places is kept for a newcomer.")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "2" }));
    expect(screen.getByText("2 of 4 places are kept for a newcomer.")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "0" }));
    expect(screen.getByText("All four places go to whoever fits best.")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("FAQ says plainly that payments are simulated", async () => {
    const user = userEvent.setup();
    render(<Faq />);
    expect(FAQ).toHaveLength(6);
    await user.click(screen.getByRole("button", { name: "Is the money real?" }));
    expect(screen.getByText(/simulated/)).toBeInTheDocument();
  });
});

describe("3D hero fallbacks (spec §13.12)", () => {
  const webgl = () => true;
  const gpu = () => false;
  it("uses the poster only for reduced motion, data saver, few cores, no or software WebGL", () => {
    expect(heroFallbackReason(true, { hardwareConcurrency: 8 }, webgl, gpu)).toBe("reduced-motion");
    expect(
      heroFallbackReason(
        false,
        { connection: { saveData: true }, hardwareConcurrency: 8 },
        webgl,
        gpu,
      ),
    ).toBe("save-data");
    expect(heroFallbackReason(false, { hardwareConcurrency: 2 }, webgl, gpu)).toBe("low-cores");
    expect(heroFallbackReason(false, { hardwareConcurrency: 8 }, () => false, gpu)).toBe(
      "no-webgl",
    );
    expect(heroFallbackReason(false, { hardwareConcurrency: 8 }, webgl, () => true)).toBe(
      "software-webgl",
    );
    expect(heroFallbackReason(false, { hardwareConcurrency: 8 }, webgl, gpu)).toBeNull();
  });

  function fakeDoc(renderer: string | null): Document {
    const ctx = {
      getExtension: (name: string) =>
        name === "WEBGL_debug_renderer_info" ? { UNMASKED_RENDERER_WEBGL: 1 } : null,
      getParameter: () => renderer,
    };
    return {
      createElement: () => ({ getContext: () => (renderer === null ? null : ctx) }),
    } as unknown as Document;
  }

  it("detects software rendering from the caveat probe and the renderer name", () => {
    expect(webglIsSoftware(fakeDoc(null))).toBe(true); // failIfMajorPerformanceCaveat refused
    expect(webglIsSoftware(fakeDoc("ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device)"))).toBe(true);
    expect(webglIsSoftware(fakeDoc("llvmpipe (LLVM 15.0.7, 256 bits)"))).toBe(true);
    expect(webglIsSoftware(fakeDoc("ANGLE (Intel, Vulkan 1.4 (Intel(R) Graphics))"))).toBe(false);
    expect(webglIsSoftware(fakeDoc("Apple GPU"))).toBe(false);
  });

  it("never probes WebGL when an earlier reason already applies", () => {
    let probed = false;
    heroFallbackReason(true, {}, () => {
      probed = true;
      return true;
    });
    expect(probed).toBe(false);
  });

  it("shows the poster and no WebGL canvas under reduced motion", async () => {
    window.localStorage.setItem("ds-motion", "reduce");
    server.use(
      http.get("*/api/v1/me", () =>
        HttpResponse.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 }),
      ),
      http.get("*/api/v1/public/stats", () => HttpResponse.json({})),
    );
    renderRoutes(
      [
        {
          path: "/",
          element: (
            <PreferencesProvider>
              <LandingPage />
            </PreferencesProvider>
          ),
        },
      ],
      "/",
    );
    await screen.findByRole("heading", { level: 1 });
    const visual = document.querySelector("[data-hero-mode]");
    expect(visual?.getAttribute("data-hero-mode")).toBe("poster-only");
    expect(visual?.getAttribute("data-fallback")).toBe("reduced-motion");
    window.localStorage.clear();
  });

  it("whenIdle runs the callback and can be cancelled", async () => {
    let ran = 0;
    whenIdle(() => {
      ran += 1;
    });
    const cancel = whenIdle(() => {
      ran += 10;
    });
    cancel();
    await new Promise((r) => setTimeout(r, 300));
    expect(ran).toBe(1);
  });

  it("sends signed-in visitors to their role home", async () => {
    server.use(
      http.get("*/api/v1/me", () =>
        HttpResponse.json({ id: "u1", role: "CLIENT", status: "ACTIVE", display_name: "Rahim" }),
      ),
      http.get("*/api/v1/public/stats", () => HttpResponse.json({})),
    );
    renderRoutes(
      [
        { path: "/", element: <LandingPage /> },
        { path: "/client", element: <Probe label="client home" /> },
      ],
      "/",
    );
    expect(await screen.findByText("client home")).toBeInTheDocument();
  });
});
