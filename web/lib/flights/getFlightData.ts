import {
    BAJA_RUN_FLIGHT,
    BAJA_RUN_FREEZE_MIN,
    BAJA_RUN_FLOAT_MIN,
    BAJA_RUN_RESUME_MIN,
} from './baja-run-data';
import type { FlightSample } from './types';

export type FlightTelemetryBundle = {
    samples: FlightSample[];
    freezeMin: number;
    floatMin: number;
    resumeMin: number;
};

export function getFlightTelemetry(slug: string): FlightTelemetryBundle | undefined {
    if (slug === 'baja-run') {
        return {
            samples: BAJA_RUN_FLIGHT,
            freezeMin: BAJA_RUN_FREEZE_MIN,
            floatMin: BAJA_RUN_FLOAT_MIN,
            resumeMin: BAJA_RUN_RESUME_MIN,
        };
    }
    return undefined;
}
