/**
 * Ingest manifest — what each worker step actually built this run.
 *
 * gfs_ingest.py / gefs_ingest.py / aigefs_ingest.py append to it incrementally
 * (per device, per member) so a step killed at its timeout still leaves an
 * accurate record; compute_forecasts.ts reads it to report member counts and
 * stamp them into the forecast metadata, and scripts/forecast_summary.mjs turns
 * it into the GitHub job summary. The file format is shared with the Python
 * side (gfs_ingest.manifest_*), so keep the two in step.
 */
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

export const MANIFEST_VERSION = 1;

export type ManifestSourceDevice = Record<string, unknown> & {
    built?: number;
    expected?: number;
    error?: string | null;
    seconds?: number;
};

export type ManifestSource = {
    started_at?: string;
    finished_at?: string;
    seconds?: number;
    members_expected?: number;
    devices?: Record<string, ManifestSourceDevice>;
};

export type ForecastManifest = {
    version: number;
    plan_generated_at?: string;
    sources: Record<string, ManifestSource>;
};

export const ENSEMBLE_SOURCES = ['gefs', 'aigefs'] as const;
export type EnsembleSource = (typeof ENSEMBLE_SOURCES)[number];

export function emptyManifest(planGeneratedAt?: string): ForecastManifest {
    return { version: MANIFEST_VERSION, ...(planGeneratedAt ? { plan_generated_at: planGeneratedAt } : {}), sources: {} };
}

export function readManifest(path: string): ForecastManifest | null {
    try {
        const raw = JSON.parse(readFileSync(path, 'utf8')) as Partial<ForecastManifest>;
        if (!raw || typeof raw !== 'object') return null;
        return { version: raw.version ?? MANIFEST_VERSION, plan_generated_at: raw.plan_generated_at, sources: raw.sources ?? {} };
    } catch {
        return null;
    }
}

export function writeManifest(path: string, manifest: ForecastManifest): void {
    mkdirSync(dirname(path), { recursive: true });
    const tmp = `${path}.tmp`;
    writeFileSync(tmp, JSON.stringify(manifest, null, 1));
    renameSync(tmp, path); // atomic on one filesystem: a reader never sees a torn file
}

/** Member counts for a device, per ensemble source.
 *  `members` is what is actually available (the member cubes on disk — the
 *  ground truth the compute loads), `expected` what the ingest was configured
 *  to build (from the manifest; absent when that source never started). */
export function ensembleMembers(
    memberLabels: string[],
    manifest: ForecastManifest | null,
    deviceId: string,
): { members: Record<EnsembleSource, number>; expected: Partial<Record<EnsembleSource, number>>; complete: boolean } {
    const prefix: Record<EnsembleSource, string> = { gefs: 'm', aigefs: 'a' };
    const members = { gefs: 0, aigefs: 0 } as Record<EnsembleSource, number>;
    for (const label of memberLabels) {
        for (const src of ENSEMBLE_SOURCES) if (label.startsWith(prefix[src])) members[src]++;
    }
    const expected: Partial<Record<EnsembleSource, number>> = {};
    let complete = true;
    for (const src of ENSEMBLE_SOURCES) {
        const source = manifest?.sources?.[src];
        const dev = source?.devices?.[deviceId];
        const exp = dev?.expected ?? source?.members_expected;
        if (typeof exp === 'number') {
            expected[src] = exp;
            if (members[src] < exp) complete = false;
        } else {
            /* The source never recorded anything: it did not start (or the plan
             * skipped the device). No members from it ⇒ not the full ensemble. */
            if (members[src] === 0) complete = false;
        }
    }
    return { members, expected, complete };
}

export function formatMembers(m: ReturnType<typeof ensembleMembers>): string {
    return ENSEMBLE_SOURCES
        .map((src) => `${src} ${m.members[src]}/${m.expected[src] ?? '?'}`)
        .join(', ');
}
