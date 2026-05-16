"use server"

import { Resend } from "resend"

function isValidEmail(email: string): boolean {
  const t = email.trim()
  if (t.length > 254) return false
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(t)
}

export async function subscribeLaunchUpdates(email: string) {
  const trimmed = email.trim().toLowerCase()

  if (!trimmed || !isValidEmail(trimmed)) {
    return { success: false as const, error: "Please enter a valid email address." }
  }

  const apiKey = process.env.RESEND_API_KEY

  if (!apiKey) {
    return {
      success: false as const,
      error:
        "Signup is temporarily unavailable. Reach us at shepherd.kruse@shepherdspacesystems.com for launch news.",
    }
  }

  const notifyTo =
    process.env.LAUNCH_SIGNUP_NOTIFY_EMAIL?.split(/\s*,\s*/).filter(Boolean) ?? [
      "shepherd.kruse@shepherdspacesystems.com",
    ]

  const resend = new Resend(apiKey)

  try {
    const { error } = await resend.emails.send({
      from: "Stratolink <onboarding@resend.dev>",
      to: notifyTo,
      replyTo: trimmed,
      subject: `Stratolink launch updates signup: ${trimmed}`,
      text: `Someone signed up for launch updates on stratolink.org.\n\nEmail: ${trimmed}\n`,
    })

    if (error) {
      console.error("[Stratolink] Launch signup email error:", error)
      return { success: false as const, error: "Something went wrong. Please try again in a moment." }
    }

    return { success: true as const }
  } catch (error) {
    console.error("[Stratolink] Launch signup error:", error)
    return { success: false as const, error: "Something went wrong. Please try again in a moment." }
  }
}
