import { Hero } from "@/components/hero"
import { Mission } from "@/components/mission"
import { HowItWorks } from "@/components/how-it-works"
import { Applications } from "@/components/applications"
import { AltitudeControl } from "@/components/altitude-control"
import { FutureApplications } from "@/components/future-applications"
import { Roadmap } from "@/components/roadmap"
import { Contact } from "@/components/contact"
import { Navigation } from "@/components/navigation"
import { Footer } from "@/components/footer"

export default function Page() {
  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      <main>
        <Hero />
        <Mission />
        <HowItWorks />
        <AltitudeControl />
        <Applications />
        <FutureApplications />
        <Roadmap />
        <Contact />
      </main>
      <Footer />
    </div>
  )
}
