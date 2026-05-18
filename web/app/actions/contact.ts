'use server'

import { sendEmail, isEmailConfigured } from '@/lib/email/transport'
import {
    getContactFormRecipients,
    getFromAddress,
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

    if (!isEmailConfigured()) {
        return {
            success: false,
            error: `Email service not configured. Please contact us directly at ${STRATOLINK_EMAILS.contact}`,
        }
    }

    try {
        const result = await sendEmail({
            from: getFromAddress(),
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

        if (!result.success) {
            console.error('[Stratolink] Contact form email error:', result.error)
            return { success: false, error: 'Failed to send message. Please try again.' }
        }

        return { success: true }
    } catch (error) {
        console.error('[Stratolink] Contact form error:', error)
        return { success: false, error: 'Failed to send message. Please try again.' }
    }
}
