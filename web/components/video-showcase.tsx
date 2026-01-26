'use client';

interface VideoShowcaseProps {
  src: string;
  title: string;
  description: string;
  className?: string;
}

export function VideoShowcase({ src, title, description, className = '' }: VideoShowcaseProps) {
  return (
    <div className={`rounded-sm border border-border bg-card overflow-hidden shadow-lg ${className}`}>
      {/* Header with title and description */}
      <div className="border-b border-border bg-muted/30 px-6 py-5">
        <h3 className="text-lg font-medium text-foreground tracking-tight">{title}</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground max-w-3xl">
          {description}
        </p>
      </div>

      {/* Video Container - Professional styling with dark background, non-interactive */}
      <div className="relative bg-slate-950 aspect-video overflow-hidden">
        <video
          src={src}
          autoPlay
          loop
          muted
          playsInline
          className="w-full h-full object-contain pointer-events-none"
          style={{
            backgroundColor: '#0f172a',
          }}
        >
          Your browser does not support the video tag.
        </video>
        {/* Subtle border around video */}
        <div className="absolute inset-0 pointer-events-none border border-slate-800/50" />
      </div>
    </div>
  );
}
