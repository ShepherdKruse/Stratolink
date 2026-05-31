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

/* Dark basemap: deepen night + lift day so the terminator reads on mapbox dark-v11. */
const NIGHT_RGB_DARK: [number, number, number] = [0.01, 0.015, 0.03];
const DAY_RGB_DARK: [number, number, number] = [0.52, 0.56, 0.62];

/* Twilight band in degrees of solar altitude: darkening runs from the horizon
 * (0°) to full night at astronomical twilight (−18°) — the real-world band. */
const FADE_RANGE_LIGHT: [number, number] = [0, -18];
const FADE_RANGE_DARK: [number, number] = [2, -14];

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
uniform vec3 nightColor;
uniform vec3 dayColor;
uniform float basemapMode;       /* 0 = light basemap, 1 = dark basemap */
uniform float nightStrength;
uniform float dayStrength;

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
    if (basemapMode < 0.5) {
        gl_FragColor = vec4(nightColor, nightAmt * nightStrength);
    } else {
        float dayAmt = 1.0 - nightAmt;
        vec3 rgb = mix(dayColor, nightColor, nightAmt);
        float alpha = max(nightAmt * nightStrength, dayAmt * dayStrength);
        gl_FragColor = vec4(rgb, alpha);
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
    id = 'sl-terminator';
    type = 'custom' as const;
    dataType = 'raster' as const;
    tileSize: number;

    /* Bound by Mapbox once the source is added — used to refresh tiles. */
    update?: () => void;
    clearTiles?: () => void;

    private size: number;
    private date: Date;
    private basemap: TerminatorBasemap;
    private gl: WebGLRenderingContext;
    private uniforms: Record<string, WebGLUniformLocation | null>;
    private pixels: Uint8ClampedArray;

    constructor(opts: { tileSize?: number; date?: Date; basemap?: TerminatorBasemap } = {}) {
        this.tileSize = opts.tileSize ?? 256;
        this.size = this.tileSize;
        this.date = opts.date ?? new Date();
        this.basemap = opts.basemap ?? 'light';
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
                'nightColor', 'dayColor', 'basemapMode', 'nightStrength', 'dayStrength',
            ].map(n => [n, gl.getUniformLocation(prog, n)]),
        );

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
        gl.uniform3f(this.uniforms.dayColor, ...DAY_RGB_DARK);
        gl.uniform1f(this.uniforms.basemapMode, dark ? 1 : 0);
        gl.uniform1f(this.uniforms.nightStrength, dark ? 0.92 : 1);
        gl.uniform1f(this.uniforms.dayStrength, dark ? 0.42 : 0);
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

    async loadTile(tile: { z: number; x: number; y: number }): Promise<ImageData> {
        const gl = this.gl;
        const days = toDays(this.date);
        const { sinDec, cosDec, ra } = sunCoords(days);
        const siderealTimeOffset = (RAD * (280.16 + 360.9856235 * days)) % (2 * Math.PI);
        const aabb = tileBounds3857(tile.x, tile.y, tile.z).map(v => v / EARTH_RADIUS);

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
