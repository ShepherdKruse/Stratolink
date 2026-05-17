import { createHash, randomBytes, timingSafeEqual } from 'crypto';

export function hashLaunchToken(token: string): string {
    return createHash('sha256').update(token, 'utf8').digest('hex');
}

/** URL-safe random secret for ?k= */
export function generateLaunchToken(): string {
    return randomBytes(32).toString('base64url');
}

export function timingSafeEqualHex(a: string, b: string): boolean {
    try {
        const ba = Buffer.from(a, 'hex');
        const bb = Buffer.from(b, 'hex');
        if (ba.length !== bb.length) return false;
        return timingSafeEqual(ba, bb);
    } catch {
        return false;
    }
}
