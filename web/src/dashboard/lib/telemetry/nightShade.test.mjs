import assert from 'node:assert/strict';
import test from 'node:test';
import { nightShadePixels } from '../../components/maps/terminatorRenderer.ts';

const world = { x: 0, y: 0, z: 0 };
const alpha = (pixels, size, x, y) => pixels[(y * size + x) * 4 + 3];

test('night shade follows the sun and changes tint without shifting geography', () => {
    const date = new Date('2026-03-20T12:00:00Z');
    const noon = nightShadePixels(world, 256, date, 'light');
    const midnight = nightShadePixels(world, 256, new Date('2026-03-21T00:00:00Z'), 'light');
    assert.equal(alpha(noon, 256, 128, 128), 0);
    assert.equal(alpha(noon, 256, 0, 128), 255);
    assert.equal(alpha(midnight, 256, 128, 128), 255);
    assert.equal(alpha(midnight, 256, 0, 128), 0);
    const dark = nightShadePixels(world, 256, date, 'dark');
    assert.deepEqual([...noon.slice(0, 3)], [15, 22, 41]);
    assert.deepEqual([...dark.slice(0, 3)], [3, 4, 8]);
    assert.equal(alpha(dark, 256, 128, 128), 0);
    assert.equal(alpha(dark, 256, 0, 128), 255);
});

test('polar night is in the northern winter and southern summer stays lit', () => {
    const winter = nightShadePixels(world, 256, new Date('2026-12-21T12:00:00Z'), 'light');
    assert.equal(alpha(winter, 256, 128, 0), 255);
    assert.equal(alpha(winter, 256, 128, 255), 0);
});

test('adjacent tiles retain the same gradient as the whole world at equal resolution', () => {
    const date = new Date('2026-06-21T05:00:00Z');
    const full = nightShadePixels(world, 128, date, 'light');
    for (let ty = 0; ty < 2; ty++) for (let tx = 0; tx < 2; tx++) {
        const tile = nightShadePixels({ x: tx, y: ty, z: 1 }, 64, date, 'light');
        for (let y = 0; y < 64; y++) for (let x = 0; x < 64; x++) {
            assert.equal(alpha(tile, 64, x, y), alpha(full, 128, tx * 64 + x, ty * 64 + y));
        }
    }
});
