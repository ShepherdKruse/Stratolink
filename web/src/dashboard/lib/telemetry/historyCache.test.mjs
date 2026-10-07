import assert from 'node:assert/strict';
import test from 'node:test';
import { createHistoryLoader } from './historyCache.ts';

test('overview and detail share a pending history query, then refresh only its last packet', async () => {
    const calls = [];
    let finish;
    const loader = createHistoryLoader(new Map(), async (id, since) => {
        calls.push({ id, since });
        if (calls.length === 1) return new Promise(resolve => { finish = resolve; });
        return [{ t: 200, value: 'updated' }, { t: 300, value: 'new' }];
    });
    const window = { deviceId: 'balloon', since: 100 };
    const overview = loader.load(window);
    const detail = loader.load(window, { refresh: true });
    assert.equal(overview, detail);
    assert.equal(calls.length, 1);
    finish([{ t: 100, value: 'first' }, { t: 200, value: 'old' }]);
    await overview;
    assert.equal((await loader.load(window)).length, 2);
    assert.equal(calls.length, 1);
    assert.deepEqual(await loader.load(window, { refresh: true }), [
        { t: 100, value: 'first' }, { t: 200, value: 'updated' }, { t: 300, value: 'new' },
    ]);
    assert.deepEqual(calls, [{ id: 'balloon', since: 100 }, { id: 'balloon', since: 200 }]);
});

test('empty history after registry launch falls back to real earlier packets and reuses them', async () => {
    const calls = [];
    const loader = createHistoryLoader(new Map(), async (_id, since) => {
        calls.push(since);
        return since >= 300 ? [] : [{ t: 100 }, { t: 200 }];
    });
    const window = { deviceId: 'balloon', since: 300 };
    assert.deepEqual(await loader.load(window), [{ t: 100 }, { t: 200 }]);
    assert.deepEqual(calls, [300, 0]);
    await loader.load(window, { refresh: true });
    assert.deepEqual(calls, [300, 0, 200]);
});

test('one failed device refresh preserves its cache and does not discard another device', async () => {
    let fail = false;
    const cache = new Map();
    const loader = createHistoryLoader(cache, async (id) => {
        if (fail && id === 'a') throw new Error('Temporary failure');
        return [{ t: id === 'a' ? 100 : 200 }];
    });
    const a = { deviceId: 'a', since: 0 };
    const b = { deviceId: 'b', since: 0 };
    await loader.load(a);
    fail = true;
    const results = await Promise.allSettled([
        loader.load(a, { refresh: true }), loader.load(b, { refresh: true }),
    ]);
    assert.deepEqual(results.map(result => result.status), ['rejected', 'fulfilled']);
    assert.deepEqual(cache.get('a'), [{ t: 100 }]);
    assert.deepEqual(cache.get('b'), [{ t: 200 }]);
    fail = false;
    await loader.load(a, { refresh: true });
});

test('changing the registered mission window reloads instead of appending an older mission', async () => {
    const calls = [];
    const loader = createHistoryLoader(new Map(), async (_id, since) => {
        calls.push(since);
        return [{ t: since }];
    });
    await loader.load({ deviceId: 'balloon', since: 100 });
    assert.deepEqual(await loader.load({ deviceId: 'balloon', since: 300 }), [{ t: 300 }]);
    assert.deepEqual(calls, [100, 300]);
});

test('an empty fallback is cached and does not repeat the launch query on each poll', async () => {
    const calls = [];
    const loader = createHistoryLoader(new Map(), async (_id, since) => {
        calls.push(since);
        return [];
    });
    const window = { deviceId: 'balloon', since: 100 };
    await loader.load(window);
    await loader.load(window, { refresh: true });
    assert.deepEqual(calls, [100, 0, 0]);
});
