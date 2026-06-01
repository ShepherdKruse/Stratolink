import { get, put } from '@vercel/blob';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { isBlobStorageConfigured } from './forecastStorage';

/**
 * Open-Meteo free-tier call budget (shared, persisted).
 *
 * We're on the free tier with no API key and can't pay, so we must stay under the
 * published caps (600/min, 5,000/hr, 10,000/day). Crucially an "API call" is NOT
 * one HTTP request — it's ~one per LOCATION, scaled up past 10 variables or 14
 * days (see callCostForUrl). A single multi-location grid fetch is therefore worth
 * many calls, so we meter by weighted call cost, not request count.
 *
 * A handler `primeBudget()`s once (loads the shared counter), every openMeteoFetch
 * checks/records against the in-process counter, and the handler `flushBudget()`s
 * once at the end. Best-effort across concurrent invocations (last flush wins) —
 * fine at our scale, and the margins below absorb the slack.
 */

/* Caps with headroom under the real 600 / 5,000 / 10,000 limits. */
const MINUTE_CAP = 540;
const HOUR_CAP = 4500;
const DAY_CAP = 9000;

/* `period` = floor(now / windowMs): the UTC calendar minute/hour/day index. Since
 * the epoch is UTC-midnight-aligned, these reset at UTC boundaries — matching how
 * Open-Meteo resets its limits, so our breaker clears exactly when theirs does. */
type Window = { period: number; calls: number };
type Usage = { minute: Window; hour: Window; day: Window; cursor: number };

const LOCAL_DIR = join(process.cwd(), '.forecast-cache');
const BLOB_PATH = 'open-meteo/usage.json';
const localPath = () => join(LOCAL_DIR, 'open-meteo-usage.json');

let mem: Usage | null = null;

function freshUsage(): Usage {
    return { minute: { period: 0, calls: 0 }, hour: { period: 0, calls: 0 }, day: { period: 0, calls: 0 }, cursor: 0 };
}

function rollWindow(w: Window, windowMs: number, now: number): Window {
    const period = Math.floor(now / windowMs);
    return w.period === period ? w : { period, calls: 0 };
}
function rollAll(u: Usage, now: number): Usage {
    return {
        minute: rollWindow(u.minute, 60_000, now),
        hour: rollWindow(u.hour, 3_600_000, now),
        day: rollWindow(u.day, 86_400_000, now),
        cursor: u.cursor ?? 0,
    };
}

/** Weighted call cost of an Open-Meteo URL: ~1 per location, ×(days/14) past two
 *  weeks, ×(vars/10) past ten variables. Matches the pricing-page weighting. */
export function callCostForUrl(url: string): number {
    try {
        const u = new URL(url);
        const locs = (u.searchParams.get('latitude') ?? '').split(',').filter(Boolean).length || 1;
        const fd = Number(u.searchParams.get('forecast_days') ?? '0');
        const pd = Number(u.searchParams.get('past_days') ?? '0');
        const days = Math.max(1, fd + pd);
        const vars = (u.searchParams.get('hourly') ?? '').split(',').filter(Boolean).length || 1;
        return Math.ceil(locs * Math.max(1, days / 14) * Math.max(1, vars / 10));
    } catch {
        return 1;
    }
}

async function readUsage(): Promise<Usage> {
    try {
        if (!isBlobStorageConfigured()) {
            return JSON.parse(await readFile(localPath(), 'utf8')) as Usage;
        }
        const r = await get(BLOB_PATH, { access: 'private', useCache: false });
        if (!r || r.statusCode !== 200) return freshUsage();
        return (await new Response(r.stream).json()) as Usage;
    } catch {
        return freshUsage();
    }
}

async function writeUsage(u: Usage): Promise<void> {
    try {
        const body = JSON.stringify(u);
        if (!isBlobStorageConfigured()) {
            await mkdir(LOCAL_DIR, { recursive: true });
            await writeFile(localPath(), body, 'utf8');
            return;
        }
        await put(BLOB_PATH, body, {
            access: 'private',
            addRandomSuffix: false,
            contentType: 'application/json',
            allowOverwrite: true,
        });
    } catch {
        /* non-fatal: a flaky budget store must not break (or unbound) compute */
    }
}

/** Load the shared budget into this process. Call once at the start of a handler. */
export async function primeBudget(now = Date.now()): Promise<void> {
    mem = rollAll(await readUsage(), now);
}

/** Persist the in-process budget. Call once at the end of a handler. */
export async function flushBudget(): Promise<void> {
    if (mem) await writeUsage(mem);
}

export function isPrimed(): boolean {
    return mem !== null;
}

/** Remaining calls in each window (Infinity when not primed → budget disabled). */
export function budgetRemaining(now = Date.now()): { minute: number; hour: number; day: number } {
    if (!mem) return { minute: Infinity, hour: Infinity, day: Infinity };
    mem = rollAll(mem, now);
    return {
        minute: MINUTE_CAP - mem.minute.calls,
        hour: HOUR_CAP - mem.hour.calls,
        day: DAY_CAP - mem.day.calls,
    };
}

export function recordCalls(n: number, now = Date.now()): void {
    if (!mem) return;
    mem = rollAll(mem, now);
    mem.minute.calls += n;
    mem.hour.calls += n;
    mem.day.calls += n;
}

const CAPS = { minute: MINUTE_CAP, hour: HOUR_CAP, day: DAY_CAP } as const;

/** Mark a window exhausted (remaining → 0 until it rolls). Used when Open-Meteo
 *  itself reports a limit — their counter, not ours, is the binding one — so the
 *  rest of this invocation defers instead of hammering a rejecting API. */
export function markExhausted(scope: 'minute' | 'hour' | 'day', now = Date.now()): void {
    if (!mem) return;
    mem = rollAll(mem, now);
    mem[scope].calls = CAPS[scope];
}

/** Round-robin cursor (persisted with the budget) so the cron sweeps devices
 *  across ticks instead of all at once. */
export function getCursor(): number {
    return mem?.cursor ?? 0;
}
export function setCursor(n: number): void {
    if (mem) mem.cursor = n;
}

/** Thrown by openMeteoFetch when a request would exceed a budget window. Callers
 *  defer (serve cached / 202 / resume next tick) rather than hammer the API. */
export class BudgetExceededError extends Error {
    constructor(
        public scope: 'minute' | 'hour' | 'day',
        public need: number,
        public have: number,
    ) {
        super(`Open-Meteo ${scope} budget exceeded: need ${need}, have ${have}`);
        this.name = 'BudgetExceededError';
    }
}
