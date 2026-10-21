/**
 * Homepage (spec §13.11): the front door of DevSync. Guests always land here; signed-in users
 * are redirected to their role home. Sections top to bottom as specified.
 */
import { Navigate } from "react-router";
import { useMe } from "@/features/auth/api";
import { roleHome } from "@/lib/redirects";
import { AudienceToggle } from "./Audience";
import { BackToTop } from "./BackToTop";
import { Faq } from "./Faq";
import { FairnessSpotlight } from "./FairnessSpotlight";
import { FeatureShowcase } from "./FeatureShowcase";
import { FinalCta } from "./FinalCta";
import { Hero } from "./Hero";
import { HowItWorks } from "./HowItWorks";
import { ResearchCredit } from "./ResearchCredit";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";
import { StatsStrip } from "./StatsStrip";

export default function LandingPage() {
  const me = useMe();
  if (me.data) return <Navigate to={roleHome(me.data.role, me.data.status)} replace />;
  return (
    <div className="min-h-dvh bg-bg">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:shadow-md"
      >
        Skip to content
      </a>
      <SiteHeader overlay />
      <main id="main" tabIndex={-1} className="outline-none">
        <Hero />
        <StatsStrip />
        <HowItWorks />
        <FeatureShowcase />
        <AudienceToggle />
        <FairnessSpotlight />
        <ResearchCredit />
        <Faq />
        <FinalCta />
      </main>
      <SiteFooter />
      <BackToTop />
    </div>
  );
}
