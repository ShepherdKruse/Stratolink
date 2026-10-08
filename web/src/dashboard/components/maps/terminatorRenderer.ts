/**
 * Day/night raster tiles for Mapbox. Solar position follows SunCalc
 * (Vladimir Agafonkin, BSD). Adapted from rreusser/maps/night-and-day; city-light
 * brightness comes from NASA Black Marble. Processing runs in the source worker
 * without another WebGL context or synchronous GPU pixel readbacks.
 */

const RAD = Math.PI / 180;
const OBLIQUITY = RAD * 23.4397;
const EARTH_RADIUS = 6378137.0;
const MAX_EXTENT = 20037508.342789244;  /* Web-Mercator half-circumference (m) */

export type TerminatorBasemap = 'light' | 'dark';

/* Night tint (dark navy) on light basemaps — layer `raster-opacity` scales it. */
const NIGHT_RGB_LIGHT: [number, number, number] = [0.06, 0.085, 0.16];

/* Dark basemap: a near-black night tint. */
const NIGHT_RGB_DARK: [number, number, number] = [0.01, 0.015, 0.03];

/* Twilight band in degrees of solar altitude: darkening runs from the horizon
 * (0°) to full night at astronomical twilight (−18°) — the real-world band. */
const FADE_RANGE_LIGHT: [number, number] = [0, -18];
const FADE_RANGE_DARK: [number, number] = [2, -14];

/* NASA Black Marble night-lights, hosted by rreusser (public). Clamp requests
 * to this zoom and overzoom above it by sampling the ancestor tile — keeps the
 * globe view sharp while avoiding 404s when zoomed into a mission. */
/* Public NASA Black Marble tileset (xyz, webp, z0–8). Served opaque, so we
 * request .jpg and clamp/overzoom at its maxzoom. */
const BLACK_MARBLE_TILESET = 'rreusser.black-marble';
const BM_MAXZOOM = 8;

export type TerminatorKind = 'shade' | 'lights';

function toDays(date: Date): number {
    return date.valueOf() / 86_400_000 - 0.5 + 2440588 - 2451545;
}

/** Sun right ascension + sin/cos of declination for a given instant. */
function sunCoords(d: number): { sinDec: number; cosDec: number; ra: number } {
    const M = RAD * (357.5291 + 0.98560028 * d);
    const C = RAD * (1.9148 * Math.sin(M) + 0.02 * Math.sin(2 * M) + 0.0003 * Math.sin(3 * M));
    const L = M + C + RAD * 102.9372 + Math.PI;
    const sinDec = Math.sin(OBLIQUITY) * Math.sin(L);
    return {
        sinDec,
        cosDec: Math.sqrt(Math.max(0, 1 - sinDec * sinDec)),
        ra: Math.atan2(Math.sin(L) * Math.cos(OBLIQUITY), Math.cos(L)),
    };
}

function tileBounds3857(x: number, y: number, z: number): [number, number, number, number] {
    const res = 2 ** z;
    return [
        MAX_EXTENT * (-1 + (2 * x) / res),
        MAX_EXTENT * (1 - (2 * (y + 1)) / res),
        MAX_EXTENT * (-1 + (2 * (x + 1)) / res),
        MAX_EXTENT * (1 - (2 * y) / res),
    ];
}

/** Per-pixel night amount, shared by the shade and city-light tiles. */
function nightAmounts(tile: { x: number; y: number; z: number }, size: number, date: Date, basemap: TerminatorBasemap): Float64Array {
    const amounts = new Float64Array(size * size);
    const days = toDays(date);
    const sun = sunCoords(days);
    const sidereal = (RAD * (280.16 + 360.9856235 * days)) % (2 * Math.PI);
    const [west, south, east, north] = tileBounds3857(tile.x, tile.y, tile.z).map(v => v / EARTH_RADIUS);
    const [horizon, night] = basemap === 'dark' ? FADE_RANGE_DARK : FADE_RANGE_LIGHT;
    const hourAngles = Float64Array.from({ length: size }, (_, x) => Math.cos(sidereal + west + (east - west) * (x + 0.5) / size - sun.ra));
    for (let y = 0; y < size; y++) {
        const latitude = Math.PI / 2 - 2 * Math.atan(Math.exp(-(north + (south - north) * (y + 0.5) / size)));
        const a = Math.sin(latitude) * sun.sinDec;
        const b = Math.cos(latitude) * sun.cosDec;
        for (let x = 0; x < size; x++) {
            const altitude = Math.asin(Math.max(-1, Math.min(1, a + b * hourAngles[x]))) / RAD;
            const t = Math.max(0, Math.min(1, (altitude - horizon) / (night - horizon)));
            amounts[y * size + x] = t * t * t * (t * (t * 6 - 15) + 10);
        }
    }
    return amounts;
}

/** Same solar gradient as the original shader, without a GPU readback. */
export function nightShadePixels(tile: { x: number; y: number; z: number }, size: number, date: Date, basemap: TerminatorBasemap): Uint8ClampedArray<ArrayBuffer> {
    const amounts = nightAmounts(tile, size, date, basemap);
    const pixels = new Uint8ClampedArray(size * size * 4);
    const color = (basemap === 'dark' ? NIGHT_RGB_DARK : NIGHT_RGB_LIGHT).map(channel => Math.round(channel * 255));
    for (let i = 0; i < amounts.length; i++) {
        pixels[i * 4] = color[0];
        pixels[i * 4 + 1] = color[1];
        pixels[i * 4 + 2] = color[2];
        pixels[i * 4 + 3] = 255 * amounts[i];
    }
    return pixels;
}

/** Match the shader's linear texture sampling and brightness-weighted alpha. */
export function nightLightPixels(tile: { x: number; y: number; z: number }, size: number, date: Date, basemap: TerminatorBasemap,
    texture: Pick<ImageData, 'data' | 'width' | 'height'>, scale = 1, offX = 0, offY = 0): Uint8ClampedArray<ArrayBuffer> {
    const amounts = nightAmounts(tile, size, date, basemap);
    const pixels = new Uint8ClampedArray(size * size * 4);
    const { data, width, height } = texture;
    for (let y = 0; y < size; y++) {
        const sy = (offY + (y + 0.5) / size * scale) * height - 0.5;
        const fy = Math.floor(sy), ty = sy - fy;
        const y0 = Math.max(0, Math.min(height - 1, fy)), y1 = Math.max(0, Math.min(height - 1, fy + 1));
        for (let x = 0; x < size; x++) {
            const sx = (offX + (x + 0.5) / size * scale) * width - 0.5;
            const fx = Math.floor(sx), tx = sx - fx;
            const x0 = Math.max(0, Math.min(width - 1, fx)), x1 = Math.max(0, Math.min(width - 1, fx + 1));
            const top = (y0 * width + x0) * 4, topRight = (y0 * width + x1) * 4;
            const bottom = (y1 * width + x0) * 4, bottomRight = (y1 * width + x1) * 4;
            const offset = (y * size + x) * 4;
            let luminance = 0;
            for (let c = 0; c < 3; c++) {
                const a = data[top + c] + (data[topRight + c] - data[top + c]) * tx;
                const b = data[bottom + c] + (data[bottomRight + c] - data[bottom + c]) * tx;
                const color = a + (b - a) * ty;
                pixels[offset + c] = color;
                luminance += color * (c === 0 ? 0.299 : c === 1 ? 0.587 : 0.114);
            }
            pixels[offset + 3] = Math.min(255, luminance * 1.6) * amounts[y * size + x];
        }
    }
    return pixels;
}

export type TerminatorOptions = {
        /** Mapbox source id (must match the id passed to map.addSource). */
        id?: string;
        /** Which component this source renders: the night 'shade' or the city
         *  'lights'. They live in separate layers so the lights can fade by zoom
         *  while the shade stays constant. */
        kind?: TerminatorKind;
        tileSize?: number;
        date?: Date;
        basemap?: TerminatorBasemap;
        /** Mapbox token — required to fetch black-marble night-lights tiles. */
        token?: string;
        /** Composite black-marble night lights (only meaningful for 'lights'). */
        blackMarble?: boolean;
        /** Cap tile zoom (Mapbox overzooms beyond it). */
        maxzoom?: number;
    };

export class TerminatorRenderer {
    private options: TerminatorOptions;
    private date: Date;
    private basemap: TerminatorBasemap;
    private tileSize: number;
    private context?: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
    private controller = new AbortController();
    private bmCache = new Map<string, Promise<ImageData | null>>();

    constructor(options: TerminatorOptions = {}) {
        this.options = options;
        this.date = options.date ?? new Date();
        this.basemap = options.basemap ?? 'light';
        this.tileSize = options.tileSize ?? 256;
    }

    dispose(): void {
        this.controller.abort();
        this.bmCache.clear();
        if (this.context) this.context.canvas.width = this.context.canvas.height = 0;
        this.context = undefined;
    }

    setBasemap(basemap: TerminatorBasemap): void { this.basemap = basemap; }
    setDate(date: Date): void { this.date = date; }

    private async decode(blob: Blob): Promise<ImageData> {
        const bitmap = await createImageBitmap(blob);
        try {
            this.controller.signal.throwIfAborted();
            if (!this.context) {
                const canvas = typeof document === 'undefined' ? new OffscreenCanvas(bitmap.width, bitmap.height) : document.createElement('canvas');
                this.context = canvas.getContext('2d', { willReadFrequently: true }) as CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
                if (!this.context) throw new Error('Canvas unavailable for night-light tiles');
            }
            const { canvas } = this.context;
            if (canvas.width !== bitmap.width) canvas.width = bitmap.width;
            if (canvas.height !== bitmap.height) canvas.height = bitmap.height;
            this.context.drawImage(bitmap, 0, 0);
            return this.context.getImageData(0, 0, bitmap.width, bitmap.height);
        } finally { bitmap.close(); }
    }

    private blackMarbleTile(z: number, x: number, y: number) {
        const zz = Math.min(z, BM_MAXZOOM), dz = z - zz;
        const ax = x >> dz, ay = y >> dz;
        const scale = 1 / 2 ** dz;
        const key = `${zz}/${ax}/${ay}`;
        let promise = this.bmCache.get(key);
        if (!promise) {
            const url = `https://api.mapbox.com/v4/${BLACK_MARBLE_TILESET}/${zz}/${ax}/${ay}.jpg?access_token=${this.options.token}`;
            promise = fetch(url, { referrerPolicy: 'origin', signal: this.controller.signal })
                .then(r => r.ok ? r.blob() : null)
                .then(blob => blob ? this.decode(blob) : null)
                .catch(() => null);
            this.bmCache.set(key, promise);
            while (this.bmCache.size > 64) this.bmCache.delete(this.bmCache.keys().next().value!);
        }
        return { promise, scale, offX: (x - (ax << dz)) * scale, offY: (y - (ay << dz)) * scale };
    }

    async loadTile(tile: { z: number; x: number; y: number }): Promise<ImageData> {
        this.controller.signal.throwIfAborted();
        const size = this.tileSize;
        if (this.options.kind !== 'lights') return new ImageData(nightShadePixels(tile, size, this.date, this.basemap), size, size);
        if (!this.options.blackMarble || !this.options.token) return new ImageData(size, size);
        const sample = this.blackMarbleTile(tile.z, tile.x, tile.y);
        const texture = await sample.promise;
        this.controller.signal.throwIfAborted();
        return texture ? new ImageData(nightLightPixels(tile, size, this.date, this.basemap, texture, sample.scale, sample.offX, sample.offY), size, size)
            : new ImageData(size, size);
    }
}
