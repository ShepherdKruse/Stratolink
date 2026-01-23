"use client"

import type React from "react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { submitContactForm } from "@/app/actions/contact"

export function Contact() {
  const [formData, setFormData] = useState({
    name: "",
    organization: "",
    email: "",
    message: "",
  })
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    setStatus(null)

    const result = await submitContactForm(formData)

    if (result.success) {
      setStatus({ type: "success", message: "Message sent successfully. We'll be in touch soon." })
      setFormData({ name: "", organization: "", email: "", message: "" })
    } else {
      setStatus({ type: "error", message: result.error || "Something went wrong." })
    }

    setIsSubmitting(false)
  }

  return (
    <section id="contact" className="py-24 sm:py-32">
      <div className="mx-auto max-w-5xl px-6 sm:px-8">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-3xl font-light tracking-tight text-foreground sm:text-4xl">Contact</h2>
          <p className="mt-6 text-base leading-relaxed text-muted-foreground">
            Interested in collaborating, deploying sensors, or accessing atmospheric data? Get in touch with our team.
          </p>
        </div>

        <div className="mx-auto mt-12 max-w-xl">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <Label htmlFor="name" className="text-sm font-light text-foreground">
                Name
              </Label>
              <Input
                id="name"
                type="text"
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="mt-2"
              />
            </div>
            <div>
              <Label htmlFor="organization" className="text-sm font-light text-foreground">
                Organization
              </Label>
              <Input
                id="organization"
                type="text"
                value={formData.organization}
                onChange={(e) => setFormData({ ...formData, organization: e.target.value })}
                className="mt-2"
              />
            </div>
            <div>
              <Label htmlFor="email" className="text-sm font-light text-foreground">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                required
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="mt-2"
              />
            </div>
            <div>
              <Label htmlFor="message" className="text-sm font-light text-foreground">
                Message
              </Label>
              <Textarea
                id="message"
                required
                rows={5}
                value={formData.message}
                onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                className="mt-2"
              />
            </div>

            {status && (
              <div
                className={`rounded-md p-4 text-sm ${
                  status.type === "success"
                    ? "bg-green-50 text-green-800 border border-green-200"
                    : "bg-red-50 text-red-800 border border-red-200"
                }`}
              >
                {status.message}
              </div>
            )}

            <Button
              type="submit"
              size="lg"
              disabled={isSubmitting}
              className="w-full border border-primary bg-primary font-normal text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {isSubmitting ? "Sending..." : "Send Message"}
            </Button>
          </form>

          <div className="mt-8 border-t pt-8 text-center">
            <p className="text-sm text-muted-foreground">
              Or reach us directly at{" "}
              <a href="mailto:contact@stratolink.org" className="font-normal text-foreground underline">
                contact@stratolink.org
              </a>
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
