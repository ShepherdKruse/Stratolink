export function WorkflowDiagram() {
  return (
    <div className="mx-auto max-w-4xl">
      <svg className="h-auto w-full" viewBox="0 0 800 300" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Release */}
        <rect
          x="20"
          y="120"
          width="140"
          height="60"
          rx="4"
          stroke="currentColor"
          strokeWidth="2"
          className="text-slate-700"
          fill="white"
        />
        <text x="90" y="155" textAnchor="middle" className="fill-slate-700 text-sm font-medium">
          Release
        </text>

        {/* Arrow */}
        <path d="M 170 150 L 210 150" stroke="currentColor" strokeWidth="2" className="text-slate-400" />
        <path
          d="M 205 145 L 210 150 L 205 155"
          stroke="currentColor"
          strokeWidth="2"
          className="text-slate-400"
          fill="none"
        />

        {/* Measure */}
        <rect
          x="220"
          y="120"
          width="140"
          height="60"
          rx="4"
          stroke="currentColor"
          strokeWidth="2"
          className="text-slate-700"
          fill="white"
        />
        <text x="290" y="155" textAnchor="middle" className="fill-slate-700 text-sm font-medium">
          Measure
        </text>

        {/* Arrow */}
        <path d="M 370 150 L 410 150" stroke="currentColor" strokeWidth="2" className="text-slate-400" />
        <path
          d="M 405 145 L 410 150 L 405 155"
          stroke="currentColor"
          strokeWidth="2"
          className="text-slate-400"
          fill="none"
        />

        {/* Transmit */}
        <rect
          x="420"
          y="120"
          width="140"
          height="60"
          rx="4"
          stroke="currentColor"
          strokeWidth="2"
          className="text-slate-700"
          fill="white"
        />
        <text x="490" y="155" textAnchor="middle" className="fill-slate-700 text-sm font-medium">
          Transmit
        </text>

        {/* Arrow */}
        <path d="M 570 150 L 610 150" stroke="currentColor" strokeWidth="2" className="text-slate-400" />
        <path
          d="M 605 145 L 610 150 L 605 155"
          stroke="currentColor"
          strokeWidth="2"
          className="text-slate-400"
          fill="none"
        />

        {/* Validate */}
        <rect
          x="620"
          y="120"
          width="140"
          height="60"
          rx="4"
          stroke="currentColor"
          strokeWidth="2"
          className="text-slate-700"
          fill="white"
        />
        <text x="690" y="155" textAnchor="middle" className="fill-slate-700 text-sm font-medium">
          Validate
        </text>

        {/* Feedback loop */}
        <path
          d="M 690 70 L 690 110"
          stroke="currentColor"
          strokeWidth="2"
          strokeDasharray="4,4"
          className="text-slate-400"
        />
        <path
          d="M 90 70 L 690 70"
          stroke="currentColor"
          strokeWidth="2"
          strokeDasharray="4,4"
          className="text-slate-400"
        />
        <path
          d="M 90 70 L 90 110"
          stroke="currentColor"
          strokeWidth="2"
          strokeDasharray="4,4"
          className="text-slate-400"
        />
        <path
          d="M 85 105 L 90 110 L 95 105"
          stroke="currentColor"
          strokeWidth="2"
          className="text-slate-400"
          fill="none"
        />

        <text x="400" y="60" textAnchor="middle" className="fill-slate-500 text-xs">
          Continuous improvement loop
        </text>
      </svg>
    </div>
  )
}
