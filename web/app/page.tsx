import { HeroScroll } from "@/components/hero-globe/HeroScroll"
import { Mission } from "@/components/mission"
import { HowItWorks } from "@/components/how-it-works"
import { DashboardShowcase } from "@/components/dashboard-showcase"
import { Applications } from "@/components/applications"
import { FutureApplications } from "@/components/future-applications"
import { Roadmap } from "@/components/roadmap"
import { LaunchUpdates } from "@/components/launch-updates"
import { Contact } from "@/components/contact"
import { Navigation } from "@/components/navigation"
import { Footer } from "@/components/footer"

export default function Page() {
  return (
    <div className="home-instrument min-h-screen bg-background">
      <Navigation />
      <main>
        <HeroScroll />
        <Mission />
        <HowItWorks />
        <DashboardShowcase />
        <Applications />
        <FutureApplications />
        <Roadmap />
        <LaunchUpdates />
        <Contact />
      </main>
      <Footer />
    </div>
  )
}
