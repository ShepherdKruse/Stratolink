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

      {/* Video Container - Seamless integration with site styling */}
      <div className="relative bg-background aspect-video overflow-hidden">
        <video
          src={src}
          autoPlay
          loop
          muted
          playsInline
          className="w-full h-full object-cover pointer-events-none"
        >
          Your browser does not support the video tag.
        </video>
      </div>
    </div>
  );
}
