/**
 * Stratolink public email addresses and Resend defaults.
 *
 * Google Workspace handles human inboxes (contact@, info@, help@).
 * Resend sends website form notifications — verify stratolink.org in Resend
 * and add their SPF/DKIM alongside Google's (see .env.local.example).
 */

export const STRATOLINK_EMAILS = {
    contact: 'contact@stratolink.org',
    info: 'info@stratolink.org',
    help: 'help@stratolink.org',
    /** Transactional "from" for contact form / launch signup (Resend-verified domain). */
    notifications: 'notifications@stratolink.org',
} as const

export type StratolinkEmailRole = keyof typeof STRATOLINK_EMAILS

/** Comma-separated in CONTACT_FORM_TO env; defaults to contact + info. */
export function getContactFormRecipients(): string[] {
    const raw =
        process.env.CONTACT_FORM_TO ??
        `${STRATOLINK_EMAILS.contact},${STRATOLINK_EMAILS.info}`
    return raw
        .split(',')
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean)
}

/** Comma-separated in LAUNCH_SIGNUP_NOTIFY_EMAIL env. */
export function getLaunchSignupNotifyRecipients(): string[] {
    const raw =
        process.env.LAUNCH_SIGNUP_NOTIFY_EMAIL ?? STRATOLINK_EMAILS.contact
    return raw
        .split(',')
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean)
}

export function getResendFromAddress(): string {
    return (
        process.env.RESEND_FROM_EMAIL ??
        `Stratolink <${STRATOLINK_EMAILS.notifications}>`
    )
}

export function getPublicContactEmails(): readonly [string, string, string] {
    return [STRATOLINK_EMAILS.contact, STRATOLINK_EMAILS.info, STRATOLINK_EMAILS.help]
}
