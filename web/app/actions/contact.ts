'use server'

import { Resend } from 'resend'
import {
    getContactFormRecipients,
    getResendFromAddress,
    STRATOLINK_EMAILS,
} from '@/lib/email/stratolink'

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
            error: `Email service not configured. Please contact us directly at ${STRATOLINK_EMAILS.contact}`,
        }
    }

    const resend = new Resend(apiKey)

    try {
        const { error } = await resend.emails.send({
            from: getResendFromAddress(),
            to: getContactFormRecipients(),
            replyTo: email,
            subject: `Stratolink Contact: ${name}${organization ? ` (${organization})` : ""}`,
            text: `
Name: ${name}
Organization: ${organization || 'Not provided'}
Email: ${email}

Message:
${message}
            `.trim(),
        })

        if (error) {
            console.error('[Stratolink] Contact form email error:', error)
            return { success: false, error: 'Failed to send message. Please try again.' }
        }

        return { success: true }
    } catch (error) {
        console.error('[Stratolink] Contact form error:', error)
        return { success: false, error: 'Failed to send message. Please try again.' }
    }
}
