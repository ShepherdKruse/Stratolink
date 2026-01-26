import { VideoShowcase } from "./video-showcase"

export function Roadmap() {
  return (
    <section id="roadmap" className="border-b py-24 sm:py-32">
      <div className="mx-auto max-w-5xl px-6 sm:px-8">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-3xl font-light tracking-tight text-foreground sm:text-4xl">Development Roadmap</h2>
          <div className="mt-8 space-y-6 text-base leading-relaxed text-muted-foreground">
            <p>
              Our development priorities focus on expanding data coverage, improving telemetry reliability, and building
              tools that enable researchers to access and analyze atmospheric observations. Future releases will include
              interactive tracking interfaces, historical data queries, and automated quality control pipelines.
            </p>
            <p>
              We're working toward a publicly accessible platform with documented APIs, standardized data formats
              compatible with common atmospheric science tools, and collaborative features for the research community.
            </p>
          </div>
        </div>

        <div className="mt-16">
          <VideoShowcase
            src="/videos/balloon_trajectories_quiver_14_days_30_balloons_robinson_coverage.mp4"
            title="Fleet Coverage Simulation"
            description="14-day trajectory simulation showing 30 balloon fleet coverage patterns. The visualization demonstrates how distributed balloon platforms create comprehensive atmospheric observation coverage over time, with quiver plots indicating wind vector fields and trajectory paths showing balloon drift patterns across the stratosphere."
          />
        </div>

        <div className="mt-16 grid gap-12 sm:grid-cols-3">
          <div>
            <div className="text-sm font-light text-muted-foreground">Phase 1</div>
            <h3 className="mt-2 text-base font-normal text-foreground">Pilot Operations</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Initial balloon deployments, sensor validation campaigns, and partnerships with atmospheric research
              institutions.
            </p>
          </div>
          <div>
            <div className="text-sm font-light text-muted-foreground">Phase 2</div>
            <h3 className="mt-2 text-base font-normal text-foreground">Data Platform Launch</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Public data archive, API access for researchers, and expanded coverage across priority observation
              regions.
            </p>
          </div>
          <div>
            <div className="text-sm font-light text-muted-foreground">Phase 3</div>
            <h3 className="mt-2 text-base font-normal text-foreground">Operational Network</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Continuous observation capabilities, real-time data feeds, and collaborative tools for the atmospheric
              science community.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
