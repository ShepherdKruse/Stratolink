'use server'

import { sendEmail, isEmailConfigured } from '@/lib/email/transport'
import {
    getLaunchSignupNotifyRecipients,
    getFromAddress,
    STRATOLINK_EMAILS,
} from '@/lib/email/stratolink'

function isValidEmail(email: string): boolean {
    const t = email.trim()
    if (t.length > 254) return false
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(t)
}

export async function subscribeLaunchUpdates(email: string) {
    const trimmed = email.trim().toLowerCase()

    if (!trimmed || !isValidEmail(trimmed)) {
        return { success: false as const, error: 'Please enter a valid email address.' }
    }

    if (!isEmailConfigured()) {
        return {
            success: false as const,
            error: `Signup is temporarily unavailable. Reach us at ${STRATOLINK_EMAILS.contact} for launch news.`,
        }
    }

    try {
        const result = await sendEmail({
            from: getFromAddress(),
            to: getLaunchSignupNotifyRecipients(),
            replyTo: trimmed,
            subject: `Stratolink launch updates signup: ${trimmed}`,
            text: `Someone signed up for launch updates on stratolink.org.\n\nEmail: ${trimmed}\n`,
        })

        if (!result.success) {
            console.error('[Stratolink] Launch signup email error:', result.error)
            return { success: false as const, error: 'Something went wrong. Please try again in a moment.' }
        }

        return { success: true as const }
    } catch (error) {
        console.error('[Stratolink] Launch signup error:', error)
        return { success: false as const, error: 'Something went wrong. Please try again in a moment.' }
    }
}
