import assert from 'node:assert/strict';
import test from 'node:test';
import { adjacentPacketTime, historyRange } from './timelineHistory.ts';

const rows = times => times.map(t => ({ t }));

test('fleet range spans mixed histories, including empty and single-packet flights', () => {
    assert.equal(historyRange([]), null);
    assert.equal(historyRange([[], []]), null);
    assert.deepEqual(historyRange([rows([20, 40]), [], rows([0]), rows([15, 90])]), { start: 0, end: 90 });
    assert.deepEqual(historyRange([rows([0])]), { start: 0, end: 0 });
});

test('keyboard replay skips equal timestamps and crosses gaps between balloons', () => {
    const histories = [rows([10, 20, 20, 50]), rows([5, 20, 30, 60]), []];
    for (const [time, previous, next] of [[0, null, 5], [5, null, 10], [20, 10, 30], [25, 20, 30], [60, 50, null], [100, 60, null]]) {
        assert.equal(adjacentPacketTime(histories, time, 'previous'), previous);
        assert.equal(adjacentPacketTime(histories, time, 'next'), next);
    }
    assert.equal(adjacentPacketTime([[]], 0, 'next'), null);
});

test('fleet navigation matches a merged timeline without changing packet arrays', () => {
    const histories = Array.from({ length: 70 }, (_, i) => Object.freeze(rows(Array.from({ length: i % 13 }, (_, j) => (i * 19 + j * 37) % 1000).sort((a, b) => a - b))));
    const merged = histories.flat().sort((a, b) => a.t - b.t);
    assert.deepEqual(historyRange(histories), { start: merged[0].t, end: merged.at(-1).t });
    for (let time = -10; time <= 1010; time += 7) {
        assert.equal(adjacentPacketTime(histories, time, 'previous'), merged.findLast(row => row.t < time)?.t ?? null);
        assert.equal(adjacentPacketTime(histories, time, 'next'), merged.find(row => row.t > time)?.t ?? null);
    }
});

test('range and keyboard lookup inspect endpoints and logarithmic candidates, not all fleet packets', () => {
    let reads = 0;
    const histories = Array.from({ length: 100 }, (_, i) => Array.from({ length: 10000 }, (_, j) => ({ get t() { reads++; return j * 100 + i; } })));
    assert.deepEqual(historyRange(histories), { start: 0, end: 999999 });
    assert.equal(reads, 200);
    reads = 0;
    assert.equal(adjacentPacketTime(histories, 500000, 'previous'), 499999);
    assert.ok(reads < 1600, `inspected ${reads} timestamps`);
    reads = 0;
    assert.equal(adjacentPacketTime(histories, 500000, 'next'), 500001);
    assert.ok(reads < 1600, `inspected ${reads} timestamps`);
});
