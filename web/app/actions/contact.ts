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

    console.log('[v0] Contact form submitted:', { name, organization, email })
    console.log('[v0] SMTP_USER configured:', !!process.env.SMTP_USER)
    console.log('[v0] SMTP_PASS configured:', !!process.env.SMTP_PASS)

    if (!isEmailConfigured()) {
        console.log('[v0] Email not configured - SMTP credentials missing')
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

        console.log('[v0] Email result:', result)
        
        if (!result.success) {
            console.error('[v0] Contact form email error:', result.error)
            return { success: false, error: 'Failed to send message. Please try again.' }
        }

        console.log('[v0] Contact form email sent successfully')
        return { success: true }
    } catch (error) {
        console.error('[Stratolink] Contact form error:', error)
        return { success: false, error: 'Failed to send message. Please try again.' }
    }
}
