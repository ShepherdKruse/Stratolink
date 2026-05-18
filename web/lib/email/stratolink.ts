/**
 * Stratolink public email addresses and email configuration.
 *
 * Google Workspace handles all email via SMTP.
 * Set SMTP_USER and SMTP_PASS environment variables for sending.
 */

export const STRATOLINK_EMAILS = {
    contact: 'contact@stratolink.org',
    info: 'info@stratolink.org',
    help: 'help@stratolink.org',
    /** Transactional "from" for contact form / launch signup. */
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

export function getFromAddress(): string {
    return (
        process.env.SMTP_FROM_EMAIL ??
        `Stratolink <${STRATOLINK_EMAILS.notifications}>`
    )
}

export function getPublicContactEmails(): readonly [string, string, string] {
    return [STRATOLINK_EMAILS.contact, STRATOLINK_EMAILS.info, STRATOLINK_EMAILS.help]
}
