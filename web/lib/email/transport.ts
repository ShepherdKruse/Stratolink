/**
 * Nodemailer transport configured for Google Workspace SMTP.
 * 
 * Required environment variables:
 * - SMTP_USER: Your Google Workspace email (e.g., contact@stratolink.org)
 * - SMTP_PASS: App password (generate at https://myaccount.google.com/apppasswords)
 */

import nodemailer from 'nodemailer'

export interface EmailOptions {
    from: string
    to: string | string[]
    replyTo?: string
    subject: string
    text: string
    html?: string
}

let transporter: nodemailer.Transporter | null = null

function getTransporter(): nodemailer.Transporter {
    if (transporter) return transporter

    const user = process.env.SMTP_USER
    const pass = process.env.SMTP_PASS

    if (!user || !pass) {
        throw new Error('SMTP_USER and SMTP_PASS environment variables are required')
    }

    transporter = nodemailer.createTransport({
        host: 'smtp.gmail.com',
        port: 587,
        secure: false, // Use STARTTLS
        auth: {
            user,
            pass,
        },
    })

    return transporter
}

export async function sendEmail(options: EmailOptions): Promise<{ success: boolean; error?: string }> {
    try {
        const transport = getTransporter()
        
        await transport.sendMail({
            from: options.from,
            to: Array.isArray(options.to) ? options.to.join(', ') : options.to,
            replyTo: options.replyTo,
            subject: options.subject,
            text: options.text,
            html: options.html,
        })

        return { success: true }
    } catch (error) {
        console.error('[Stratolink] Email send error:', error)
        return { 
            success: false, 
            error: error instanceof Error ? error.message : 'Failed to send email' 
        }
    }
}

export function isEmailConfigured(): boolean {
    return Boolean(process.env.SMTP_USER && process.env.SMTP_PASS)
}
