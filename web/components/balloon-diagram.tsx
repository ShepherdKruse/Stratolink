export function BalloonDiagram() {
  return (
    <svg
      className="h-full w-full"
      viewBox="0 0 1200 600"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid slice"
    >
      {/* Contour lines representing atmospheric layers */}
      <path d="M 0 100 Q 300 90 600 100 T 1200 100" stroke="currentColor" strokeWidth="1" className="text-slate-900" />
      <path d="M 0 200 Q 300 190 600 200 T 1200 200" stroke="currentColor" strokeWidth="1" className="text-slate-900" />
      <path d="M 0 300 Q 300 310 600 300 T 1200 300" stroke="currentColor" strokeWidth="1" className="text-slate-900" />
      <path d="M 0 400 Q 300 390 600 400 T 1200 400" stroke="currentColor" strokeWidth="1" className="text-slate-900" />
      <path d="M 0 500 Q 300 510 600 500 T 1200 500" stroke="currentColor" strokeWidth="1" className="text-slate-900" />

      {/* Balloon trajectory path */}
      <path
        d="M 150 550 Q 300 400 450 250 T 750 150 Q 900 100 1050 120"
        stroke="currentColor"
        strokeWidth="2"
        strokeDasharray="5,5"
        className="text-slate-900"
      />

      {/* Balloon positions along trajectory */}
      <circle cx="150" cy="550" r="4" fill="currentColor" className="text-slate-900" />
      <circle cx="450" cy="250" r="4" fill="currentColor" className="text-slate-900" />
      <circle cx="750" cy="150" r="4" fill="currentColor" className="text-slate-900" />
      <circle cx="1050" cy="120" r="4" fill="currentColor" className="text-slate-900" />
    </svg>
  )
}
