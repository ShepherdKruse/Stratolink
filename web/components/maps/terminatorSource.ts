/**
 * Day/night terminator as a Mapbox custom raster source.
 *
 * Technique adapted from Ricky Reusser's "night and day" map
 * (https://github.com/rreusser/maps/tree/main/night-and-day): for each map
 * tile, a tiny WebGL quad computes the sun's altitude per pixel from the tile's
 * Web-Mercator bounds and maps it through `smootherstep` to a night opacity.
 * Mapbox drapes the resulting raster tiles on the globe natively, so the
 * terminator is a perfectly smooth, per-pixel gradient at any zoom — no polygon
 * banding, no in-shader unprojection.
 *
 * On dark basemaps it can also composite NASA Black Marble night-lights
 * (`rreusser.black-marble`) into the night side: the same shader samples the
 * black-marble raster tile and uses the computed night amount as its alpha, so
 * the city lights appear exactly where it's dark and fade out across the
 * twilight band — no day-side bleed. Tiles failing to load fall back to a flat
 * night tint per-tile.
 *
 * Solar position math is SunCalc (Vladimir Agafonkin, BSD), pared to the sun.
 */
import type { CustomSourceInterface } from 'mapbox-gl';

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

const VERT = `precision highp float;
attribute vec2 xy;
void main () { gl_Position = vec4(xy, 0.0, 1.0); }`;

const FRAG = `precision highp float;
uniform vec2 resolution;
uniform vec3 sunCoords;          /* sinDec, cosDec, ra */
uniform vec4 aabb;               /* xmin, ymin, xmax, ymax  (Mercator / earthRadius) */
uniform float siderealTimeOffset;
uniform vec2 fadeRange;          /* horizon, full-night altitude (deg) */
uniform vec3 nightColor;         /* night-shade tint (per theme) */
uniform float outputLights;      /* 1 = render city lights, 0 = render night shade */
uniform sampler2D blackMarble;   /* night-lights texture for this tile */
uniform float useBlackMarble;    /* 1 = the blackMarble texture is bound */
uniform vec2 bmUvScale;          /* overzoom: sub-rect scale within the texture */
uniform vec2 bmUvOffset;         /* overzoom: sub-rect offset within the texture */

vec2 toWgs84Rad (vec2 m) {
    return vec2(m.x, ${Math.PI / 2.0} - 2.0 * atan(exp(-m.y)));
}
float sunAltitude (vec2 lngLat) {
    float H = siderealTimeOffset + lngLat.x - sunCoords.z;
    return asin(clamp(sin(lngLat.y) * sunCoords.x + cos(lngLat.y) * sunCoords.y * cos(H), -1.0, 1.0));
}
float smootherstep (float e0, float e1, float v) {
    float x = clamp((v - e0) / (e1 - e0), 0.0, 1.0);
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0);
}
void main () {
    vec2 uv = gl_FragCoord.xy / resolution;
    vec2 m = aabb.xw + (aabb.zy - aabb.xw) * uv;       /* north at uv.y=0 (fb bottom) */
    float altDeg = sunAltitude(toWgs84Rad(m)) * ${180.0 / Math.PI};
    float nightAmt = smootherstep(fadeRange.x, fadeRange.y, altDeg);
    if (outputLights > 0.5) {
        /* LIGHTS layer — only the bright city-light pixels paint (alpha from
         * black-marble brightness), so dark/unlit areas stay transparent and the
         * basemap shows through. Lights appear on the night side (nightAmt). The
         * layer's raster-opacity (with its zoom fade) scales the intensity.
         * uv.y=0 is north (fb bottom); the texture's first row (t=0) is the
         * tile's north edge, so the v coord maps straight across. */
        if (useBlackMarble > 0.5) {
            vec2 tc = bmUvOffset + uv * bmUvScale;
            vec3 bm = texture2D(blackMarble, tc).rgb;
            float lum = dot(bm, vec3(0.299, 0.587, 0.114));
            gl_FragColor = vec4(bm, clamp(lum * 1.6, 0.0, 1.0) * nightAmt);
        } else {
            gl_FragColor = vec4(0.0);
        }
    } else {
        /* SHADE layer — a gentle dark tint on the night side. Strength comes
         * from the layer's (constant) raster-opacity. */
        gl_FragColor = vec4(nightColor, nightAmt);
    }
}`;

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader {
    const sh = gl.createShader(type)!;
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        throw new Error('terminator shader: ' + gl.getShaderInfoLog(sh));
    }
    return sh;
}

export class TerminatorSource implements CustomSourceInterface<ImageData> {
    id: string;
    type = 'custom' as const;
    dataType = 'raster' as const;
    tileSize: number;
    /* Cap tile requests; Mapbox overzooms beyond this. The terminator is a
     * smooth, low-frequency field, so a capped tile set looks identical when
     * overzoomed — and avoids the tile churn (and boundary flicker) of loading
     * ever-finer tiles as you zoom. */
    maxzoom?: number;

    /* Bound by Mapbox once the source is added — used to refresh tiles. */
    update?: () => void;
    clearTiles?: () => void;

    private kind: TerminatorKind;
    private size: number;
    private date: Date;
    private basemap: TerminatorBasemap;
    private gl: WebGLRenderingContext;
    private uniforms: Record<string, WebGLUniformLocation | null>;
    private pixels: Uint8ClampedArray;

    /* Black-marble compositing — only the 'lights' source fetches tiles. */
    private token?: string;
    private blackMarbleEnabled: boolean;
    private bmTexture: WebGLTexture | null = null;
    private bmCache = new Map<string, Promise<ImageBitmap | null>>();

    constructor(opts: {
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
    } = {}) {
        this.id = opts.id ?? 'sl-terminator';
        this.kind = opts.kind ?? 'shade';
        this.maxzoom = opts.maxzoom;
        this.tileSize = opts.tileSize ?? 256;
        this.size = this.tileSize;
        this.date = opts.date ?? new Date();
        this.basemap = opts.basemap ?? 'light';
        this.token = opts.token;
        this.blackMarbleEnabled = this.kind === 'lights' && Boolean(opts.blackMarble) && Boolean(opts.token);
        this.pixels = new Uint8ClampedArray(this.size * this.size * 4);

        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = this.size;
        const gl = canvas.getContext('webgl', {
            premultipliedAlpha: false,
            preserveDrawingBuffer: true,
            antialias: false,
        }) as WebGLRenderingContext;
        this.gl = gl;

        const prog = gl.createProgram()!;
        gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
        gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
        gl.linkProgram(prog);
        if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
            throw new Error('terminator program: ' + gl.getProgramInfoLog(prog));
        }
        gl.useProgram(prog);

        const buf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buf);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-4, -4, 4, -4, 0, 4]), gl.STATIC_DRAW);
        const xy = gl.getAttribLocation(prog, 'xy');
        gl.enableVertexAttribArray(xy);
        gl.vertexAttribPointer(xy, 2, gl.FLOAT, false, 0, 0);

        this.uniforms = Object.fromEntries(
            [
                'resolution', 'sunCoords', 'aabb', 'siderealTimeOffset', 'fadeRange',
                'nightColor', 'outputLights',
                'blackMarble', 'useBlackMarble', 'bmUvScale', 'bmUvOffset',
            ].map(n => [n, gl.getUniformLocation(prog, n)]),
        );

        gl.uniform1f(this.uniforms.outputLights, this.kind === 'lights' ? 1 : 0);

        /* Night-lights texture bound to unit 0. */
        this.bmTexture = gl.createTexture();
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, this.bmTexture);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.uniform1i(this.uniforms.blackMarble, 0);

        gl.viewport(0, 0, this.size, this.size);
        gl.disable(gl.BLEND);
        gl.uniform2f(this.uniforms.resolution, this.size, this.size);
        this.applyBasemapUniforms();
    }

    private applyBasemapUniforms(): void {
        const gl = this.gl;
        const dark = this.basemap === 'dark';
        const fade = dark ? FADE_RANGE_DARK : FADE_RANGE_LIGHT;
        gl.uniform2f(this.uniforms.fadeRange, fade[0], fade[1]);
        gl.uniform3f(this.uniforms.nightColor, ...(dark ? NIGHT_RGB_DARK : NIGHT_RGB_LIGHT));
    }

    setBasemap(basemap: TerminatorBasemap): void {
        if (this.basemap === basemap) return;
        this.basemap = basemap;
        this.applyBasemapUniforms();
        this.clearTiles?.();
        this.update?.();
    }

    setDate(date: Date): void {
        this.date = date;
        this.clearTiles?.();
        this.update?.();
    }

    /** Fetch (and cache) the black-marble tile covering this tile, clamped to
     *  BM_MAXZOOM with the overzoom sub-rect. Null on any failure. */
    private blackMarbleTile(
        z: number, x: number, y: number,
    ): { promise: Promise<ImageBitmap | null>; scale: number; offX: number; offY: number } {
        const zz = Math.min(z, BM_MAXZOOM);
        const dz = z - zz;
        const ax = x >> dz;
        const ay = y >> dz;
        const scale = 1 / 2 ** dz;
        const offX = (x - (ax << dz)) * scale;
        const offY = (y - (ay << dz)) * scale;   /* y grows south; t=0 is north — aligned */
        const key = `${zz}/${ax}/${ay}`;
        let promise = this.bmCache.get(key);
        if (!promise) {
            const url = `https://api.mapbox.com/v4/${BLACK_MARBLE_TILESET}/${zz}/${ax}/${ay}.jpg?access_token=${this.token}`;
            promise = fetch(url)
                .then(r => (r.ok ? r.blob() : null))
                .then(b => (b ? createImageBitmap(b) : null))
                .catch(() => null);
            this.bmCache.set(key, promise);
        }
        return { promise, scale, offX, offY };
    }

    async loadTile(tile: { z: number; x: number; y: number }): Promise<ImageData> {
        const gl = this.gl;

        /* Resolve the night-lights tile first (async), THEN set every uniform
         * and draw in one synchronous block so concurrent loadTile calls can't
         * interleave their uniform state. */
        let bitmap: ImageBitmap | null = null;
        let bmScale = 1, bmOffX = 0, bmOffY = 0;
        if (this.blackMarbleEnabled) {
            const t = this.blackMarbleTile(tile.z, tile.x, tile.y);
            bmScale = t.scale; bmOffX = t.offX; bmOffY = t.offY;
            bitmap = await t.promise;
        }

        const days = toDays(this.date);
        const { sinDec, cosDec, ra } = sunCoords(days);
        const siderealTimeOffset = (RAD * (280.16 + 360.9856235 * days)) % (2 * Math.PI);
        const aabb = tileBounds3857(tile.x, tile.y, tile.z).map(v => v / EARTH_RADIUS);

        if (bitmap) {
            gl.activeTexture(gl.TEXTURE0);
            gl.bindTexture(gl.TEXTURE_2D, this.bmTexture);
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, bitmap);
            gl.uniform1f(this.uniforms.useBlackMarble, 1);
            gl.uniform2f(this.uniforms.bmUvScale, bmScale, bmScale);
            gl.uniform2f(this.uniforms.bmUvOffset, bmOffX, bmOffY);
        } else {
            gl.uniform1f(this.uniforms.useBlackMarble, 0);
        }

        gl.uniform3f(this.uniforms.sunCoords, sinDec, cosDec, ra);
        gl.uniform1f(this.uniforms.siderealTimeOffset, siderealTimeOffset);
        gl.uniform4f(this.uniforms.aabb, aabb[0], aabb[1], aabb[2], aabb[3]);
        gl.drawArrays(gl.TRIANGLES, 0, 3);

        /* Synchronous readback (no async single-canvas race). readPixels row 0 is
         * the framebuffer bottom = north (our aabb maps north to uv.y=0), which is
         * exactly ImageData's top row — so a direct copy is already north-up. */
        gl.readPixels(0, 0, this.size, this.size, gl.RGBA, gl.UNSIGNED_BYTE, this.pixels);
        return new ImageData(new Uint8ClampedArray(this.pixels), this.size, this.size);
    }
}
