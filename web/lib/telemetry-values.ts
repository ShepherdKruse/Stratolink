/**
 * Convert a database/API telemetry value to a finite number without turning
 * an unavailable value into a plausible zero.
 */
export function telemetryNumber(value: unknown): number | null {
    if (value === null || value === undefined) return null;
    if (typeof value === 'string' && value.trim() === '') return null;

    const numberValue = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(numberValue) ? numberValue : null;
}
