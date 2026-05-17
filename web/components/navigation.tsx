"use client"

import Link from "next/link"
import Image from "next/image"
import { useEffect, useState } from "react"
import { Menu, X } from "lucide-react"

export function Navigation() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open])

  const close = () => setOpen(false)

  return (
    <nav className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur-sm">
      <div className="mx-auto max-w-7xl px-6 sm:px-8">
        <div className="flex h-20 items-center justify-between">
          <Link href="/" className="flex items-center" onClick={close}>
            <Image
              src="/stratolink-header-logo.png"
              alt="Stratolink"
              width={300}
              height={60}
              className="h-12 w-auto"
              priority
            />
          </Link>

          {/* Desktop nav */}
          <div className="hidden items-center gap-6 md:flex">
            <Link
              href="/activate"
              className="text-sm font-light text-muted-foreground transition-colors hover:text-foreground"
            >
              Activate Device
            </Link>
            <Link
              href="/docs"
              className="text-sm font-light text-muted-foreground transition-colors hover:text-foreground"
            >
              Docs
            </Link>
            <Link
              href="#contact"
              className="text-sm font-light text-muted-foreground transition-colors hover:text-foreground"
            >
              Contact
            </Link>
            <Link
              href="/dashboard-v2"
              className="rounded-sm bg-foreground px-4 py-2 text-sm font-medium text-background transition-colors hover:bg-foreground/90"
            >
              Mission Control
            </Link>
          </div>

          {/* Mobile nav: prominent Mission Control + hamburger */}
          <div className="flex items-center gap-2 md:hidden">
            <Link
              href="/dashboard-v2"
              onClick={close}
              className="rounded-sm bg-foreground px-3 py-2 text-xs font-medium text-background transition-colors hover:bg-foreground/90"
            >
              Mission Control
            </Link>
            <button
              type="button"
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              aria-controls="mobile-nav-menu"
              onClick={() => setOpen((v) => !v)}
              className="inline-flex h-10 w-10 items-center justify-center rounded-sm border border-border text-foreground transition-colors hover:bg-accent/50"
            >
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile dropdown */}
      {open && (
        <div
          id="mobile-nav-menu"
          className="border-t bg-background/95 backdrop-blur-sm md:hidden"
        >
          <div className="mx-auto max-w-7xl px-6 py-3 sm:px-8">
            <p className="px-3 pb-2 pt-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">
              Jump to
            </p>
            <ul className="flex flex-col gap-0.5">
              {[
                { href: "#mission", label: "Mission" },
                { href: "#how-it-works", label: "How it works" },
                { href: "#dashboard", label: "Dashboard preview" },
                { href: "#applications", label: "Applications" },
                { href: "#roadmap", label: "Roadmap" },
                { href: "#contact", label: "Contact" },
              ].map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={close}
                    className="block rounded-sm px-3 py-2.5 text-base font-light text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>

            <div className="my-3 h-px bg-border" />

            <p className="px-3 pb-2 pt-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">
              Tools
            </p>
            <ul className="flex flex-col gap-0.5">
              <li>
                <Link
                  href="/activate"
                  onClick={close}
                  className="block rounded-sm px-3 py-2.5 text-base font-light text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
                >
                  Activate device
                </Link>
              </li>
              <li>
                <Link
                  href="/docs"
                  onClick={close}
                  className="block rounded-sm px-3 py-2.5 text-base font-light text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
                >
                  Docs
                </Link>
              </li>
            </ul>
          </div>
        </div>
      )}
    </nav>
  )
}
