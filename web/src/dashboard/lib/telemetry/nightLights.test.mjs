import assert from 'node:assert/strict';
import test from 'node:test';
import { nightLightPixels, nightShadePixels, TerminatorRenderer } from '../../components/maps/terminatorRenderer.ts';

const world = { x: 0, y: 0, z: 0 };
const date = new Date('2026-03-20T12:00:00Z');
const texture = (width, height, colors) => ({ width, height, data: new Uint8ClampedArray(colors.flatMap(color => [...color, 255])) });
const rgb = (pixels, pixel) => [...pixels.slice(pixel * 4, pixel * 4 + 3)];

test('city lights retain their color and use the same night boundary as the shade', () => {
    for (const basemap of ['light', 'dark']) {
        const white = nightLightPixels(world, 128, date, basemap, texture(1, 1, [[255, 255, 255]]));
        const shade = nightShadePixels(world, 128, date, basemap);
        for (let i = 0; i < white.length; i += 4) {
            assert.equal(white[i], 255);
            assert.equal(white[i + 3], shade[i + 3]);
        }
        const black = nightLightPixels(world, 128, date, basemap, texture(1, 1, [[0, 0, 0]]));
        assert.ok(black.every(value => value === 0));
    }
});

test('city-light alpha follows weighted RGB brightness without leaking into daylight', () => {
    const red = nightLightPixels(world, 256, date, 'light', texture(1, 1, [[255, 0, 0]]));
    const night = (128 * 256) * 4;
    const day = (128 * 256 + 128) * 4;
    assert.equal(red[night + 3], Math.round(255 * 0.299 * 1.6));
    assert.equal(red[day + 3], 0);
    assert.deepEqual(rgb(red, 128 * 256 + 128), [255, 0, 0]);
});

test('linear sampling preserves north-up rows and clamps the texture edges', () => {
    const colors = texture(2, 2, [[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]]);
    const pixels = nightLightPixels(world, 4, date, 'light', colors);
    assert.deepEqual(rgb(pixels, 0), [255, 0, 0]);
    assert.deepEqual(rgb(pixels, 3), [0, 255, 0]);
    assert.deepEqual(rgb(pixels, 12), [0, 0, 255]);
    assert.deepEqual(rgb(pixels, 15), [255, 255, 255]);
    assert.deepEqual(rgb(pixels, 1), [191, 64, 0]);
    assert.deepEqual(rgb(pixels, 5), [159, 64, 64]);
});

test('overzoom samples only the requested ancestor subrectangle', () => {
    const colors = texture(4, 4, Array.from({ length: 16 }, (_, i) => [i % 4 * 60, Math.floor(i / 4) * 60, 0]));
    const pixels = nightLightPixels({ z: 9, x: 3, y: 3 }, 2, date, 'dark', colors, 0.5, 0.5, 0.5);
    assert.deepEqual(Array.from({ length: 4 }, (_, i) => rgb(pixels, i)), [[120, 120, 0], [180, 120, 0], [120, 180, 0], [180, 180, 0]]);
});

function imageDataStub(t) {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'ImageData');
    globalThis.ImageData = class {
        constructor(width, height) { this.width = width; this.height = height; this.data = new Uint8ClampedArray(width * height * 4); }
    };
    t.after(() => { if (descriptor) Object.defineProperty(globalThis, 'ImageData', descriptor); else delete globalThis.ImageData; });
}

test('unavailable light tiles remain transparent and the source cache is bounded', async t => {
    imageDataStub(t);
    let reads = 0;
    t.mock.method(globalThis, 'fetch', async (_url, options) => {
        reads++;
        assert.equal(options.referrerPolicy, 'origin');
        assert.ok(options.signal instanceof AbortSignal);
        return { ok: false };
    });
    const renderer = new TerminatorRenderer({ kind: 'lights', blackMarble: true, token: 'test', tileSize: 2 });
    t.after(() => renderer.dispose());
    for (let x = 0; x < 65; x++) {
        const image = await renderer.loadTile({ z: 8, x, y: 0 });
        assert.ok(image.data.every(value => value === 0));
    }
    await renderer.loadTile({ z: 8, x: 64, y: 0 });
    assert.equal(reads, 65);
    await renderer.loadTile({ z: 8, x: 0, y: 0 });
    assert.equal(reads, 66);
});

test('disposing a renderer cancels an in-flight fetch and rejects further tile reads', async t => {
    imageDataStub(t);
    let signal;
    t.mock.method(globalThis, 'fetch', (_url, options) => new Promise((_resolve, reject) => {
        signal = options.signal;
        signal.addEventListener('abort', () => reject(signal.reason), { once: true });
    }));
    const renderer = new TerminatorRenderer({ kind: 'lights', blackMarble: true, token: 'test' });
    const tile = renderer.loadTile(world);
    renderer.dispose();
    assert.equal(signal.aborted, true);
    await assert.rejects(tile, { name: 'AbortError' });
    await assert.rejects(renderer.loadTile(world), { name: 'AbortError' });
});

test('disabled Black Marble rendering does not fetch or create a canvas', async t => {
    imageDataStub(t);
    t.mock.method(globalThis, 'fetch', () => { throw Error('must not fetch'); });
    for (const options of [{}, { token: 'test' }, { blackMarble: true }]) {
        const renderer = new TerminatorRenderer({ kind: 'lights', tileSize: 2, ...options });
        const image = await renderer.loadTile(world);
        assert.equal(image.data.length, 16);
        assert.ok(image.data.every(value => value === 0));
        renderer.dispose();
    }
});
