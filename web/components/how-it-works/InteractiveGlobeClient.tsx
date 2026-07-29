"use client"

import dynamic from "next/dynamic"

export const InteractiveGlobeClient = dynamic(
  () => import("./InteractiveGlobe").then((m) => m.InteractiveGlobe),
  { ssr: false },
)
