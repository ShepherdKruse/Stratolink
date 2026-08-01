import { HeroScroll } from "@/components/hero-globe/HeroScroll"
import { AboutStory } from "@/components/marketing/AboutStory"
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
        <AboutStory />
        <Roadmap />
        <LaunchUpdates />
        <Contact />
      </main>
      <Footer />
    </div>
  )
}
