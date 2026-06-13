"use client"

import type React from "react"
import { useState } from "react"
import { ArrowRight, Mail } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { subscribeLaunchUpdates } from "@/app/actions/launch-updates"

/**
 * Compact launch-updates email capture. Lifted out of the old hero (which the
 * scroll-globe hero replaced) so the subscribe feature survives the redesign;
 * lives as its own quiet band above Contact.
 */
export function LaunchUpdates() {
  const [email, setEmail] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    setStatus(null)

    const result = await subscribeLaunchUpdates(email)

    if (result.success) {
      setStatus({ type: "success", message: "Thanks — we'll keep you posted on launches." })
      setEmail("")
    } else {
      setStatus({ type: "error", message: result.error || "Something went wrong." })
    }

    setIsSubmitting(false)
  }

  return (
    <section className="border-b bg-accent/20 py-16 sm:py-20">
      <div className="mx-auto max-w-2xl px-6 text-center sm:px-8">
        <div className="flex items-center justify-center gap-2 text-primary">
          <Mail className="h-4 w-4" aria-hidden />
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em]">Get launch updates</p>
        </div>
        <p className="mt-3 text-base leading-relaxed text-muted-foreground">
          Be first to hear when we fly. One email, no spam.
        </p>

        <form
          onSubmit={handleSubmit}
          className="mx-auto mt-6 flex w-full max-w-md flex-col gap-2 sm:flex-row sm:gap-2.5"
          aria-label="Get launch updates by email"
        >
          <label htmlFor="launch-email" className="sr-only">
            Email address
          </label>
          <div className="relative flex-1">
            <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <Input
              id="launch-email"
              type="email"
              name="email"
              inputMode="email"
              autoComplete="email"
              required
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-12 w-full rounded-md border-slate-300 bg-white pl-10 pr-4 text-base shadow-sm placeholder:text-slate-400 focus-visible:border-primary md:text-base"
            />
          </div>
          <Button
            type="submit"
            disabled={isSubmitting}
            className="group h-12 w-full shrink-0 rounded-md bg-primary px-5 text-sm font-semibold text-primary-foreground shadow-md transition-all hover:bg-primary/90 hover:shadow-lg disabled:opacity-60 sm:w-auto"
          >
            <span>{isSubmitting ? "Sending…" : "Notify me"}</span>
            {!isSubmitting && (
              <ArrowRight className="ml-1 h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
            )}
          </Button>
        </form>

        {status && (
          <p
            role="status"
            className={`mt-4 text-sm ${status.type === "success" ? "text-emerald-700" : "text-destructive"}`}
          >
            {status.message}
          </p>
        )}
      </div>
    </section>
  )
}
