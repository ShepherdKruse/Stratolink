"use server"

import { Resend } from "resend"

interface ContactFormData {
  name: string
  organization: string
  email: string
  message: string
}

export async function submitContactForm(formData: ContactFormData) {
  const { name, organization, email, message } = formData

  const apiKey = process.env.RESEND_API_KEY

  if (!apiKey) {
    return {
      success: false,
      error: "Email service not configured. Please contact us directly at shepherd.kruse@shepherdspacesystems.com",
    }
  }

  const resend = new Resend(apiKey)

  try {
    const { data, error } = await resend.emails.send({
      from: "Stratolink Contact <onboarding@resend.dev>",
      to: ["shepherd.kruse@shepherdspacesystems.com"],
      replyTo: email,
      subject: `Stratolink Contact: ${name}${organization ? ` (${organization})` : ""}`,
      text: `
Name: ${name}
Organization: ${organization || "Not provided"}
Email: ${email}

Message:
${message}
      `.trim(),
    })

    if (error) {
      console.error("[v0] Email error:", error)
      return { success: false, error: "Failed to send message. Please try again." }
    }

    return { success: true }
  } catch (error) {
    console.error("[v0] Contact form error:", error)
    return { success: false, error: "Failed to send message. Please try again." }
  }
}
