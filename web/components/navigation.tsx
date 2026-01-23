import Link from "next/link"
import Image from "next/image"

export function Navigation() {
  return (
    <nav className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur-sm">
      <div className="mx-auto max-w-7xl px-6 sm:px-8">
        <div className="flex h-20 items-center justify-between">
          <Link href="/" className="flex items-center">
            <Image
              src="/stratolink-header-logo.png"
              alt="Stratolink"
              width={300}
              height={60}
              className="h-12 w-auto"
              priority
            />
          </Link>
          <div className="hidden items-center gap-8 md:flex">
            <Link
              href="#mission"
              className="text-sm font-light text-muted-foreground transition-colors hover:text-foreground"
            >
              Mission
            </Link>
            <Link
              href="#how-it-works"
              className="text-sm font-light text-muted-foreground transition-colors hover:text-foreground"
            >
              How It Works
            </Link>
            <Link
              href="#applications"
              className="text-sm font-light text-muted-foreground transition-colors hover:text-foreground"
            >
              Built For
            </Link>
            <Link
              href="#future-applications"
              className="text-sm font-light text-muted-foreground transition-colors hover:text-foreground"
            >
              Future Applications
            </Link>
            <Link
              href="#roadmap"
              className="text-sm font-light text-muted-foreground transition-colors hover:text-foreground"
            >
              Roadmap
            </Link>
            <Link
              href="#contact"
              className="text-sm font-light text-muted-foreground transition-colors hover:text-foreground"
            >
              Contact
            </Link>
            <Link
              href="/docs"
              className="text-sm font-light text-muted-foreground transition-colors hover:text-foreground"
            >
              Docs
            </Link>
            <Link
              href="/dashboard"
              className="rounded-sm bg-foreground px-4 py-2 text-sm font-medium text-background transition-colors hover:bg-foreground/90"
            >
              Mission Control
            </Link>
          </div>
        </div>
      </div>
    </nav>
  )
}
