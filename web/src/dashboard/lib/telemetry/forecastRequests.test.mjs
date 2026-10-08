import assert from 'node:assert/strict';
import test from 'node:test';
import { setImmediate as flush } from 'node:timers/promises';
import { createForecastRequests } from './forecastRequests.ts';

const ok = { status: 200, data: { nominal_path: [[179, 5], [181, 6]] } };
const signal = () => new AbortController().signal;

test('forecast requests cap concurrency at four, deduplicate and prioritize a selected balloon', async () => {
    const started = [], finish = new Map();
    const pool = createForecastRequests(id => {
        started.push(id);
        return new Promise(resolve => finish.set(id, () => resolve(ok)));
    });
    const requests = Array.from({ length: 10 }, (_, i) => pool.load(String(i), signal()));
    const selected = pool.load('9', signal(), true);
    assert.deepEqual(started, ['0', '1', '2', '3']);
    finish.get('0')();
    await requests[0];
    assert.deepEqual(started, ['0', '1', '2', '3', '9']);
    finish.get('9')();
    assert.equal(await selected, await requests[9]);
    for (const id of ['1', '2', '3', '4', '5', '6', '7', '8']) {
        finish.get(id)();
        await flush();
    }
    await Promise.all(requests);
    assert.equal(started.length, 10);
});

test('cancelling one consumer preserves a shared request; abandoning all consumers cancels it', async () => {
    let requestSignal, finish;
    const pool = createForecastRequests((_id, s) => {
        requestSignal = s;
        return new Promise((resolve, reject) => {
            finish = resolve;
            s.addEventListener('abort', () => reject(s.reason), { once: true });
        });
    });
    const a = new AbortController(), b = new AbortController();
    const first = pool.load('a', a.signal), second = pool.load('a', b.signal);
    a.abort();
    await assert.rejects(first, { name: 'AbortError' });
    assert.equal(requestSignal.aborted, false);
    finish(ok);
    assert.equal(await second, ok);
    const c = new AbortController();
    const abandoned = pool.load('b', c.signal);
    c.abort();
    await assert.rejects(abandoned, { name: 'AbortError' });
    assert.equal(requestSignal.aborted, true);
    const retry = pool.load('b', signal());
    finish(ok);
    assert.equal(await retry, ok);
});

test('queued cancellations never fetch, and failed requests release their slots', async () => {
    const started = [], finish = [];
    const pool = createForecastRequests(id => {
        started.push(id);
        return new Promise((resolve, reject) => finish.push(() => id === '0' ? reject(Error('offline')) : resolve(ok)));
    });
    const requests = Array.from({ length: 4 }, (_, i) => pool.load(String(i), signal()));
    const outcomes = Promise.allSettled(requests);
    const controller = new AbortController();
    const cancelled = pool.load('cancelled', controller.signal);
    const next = pool.load('next', signal());
    controller.abort();
    await assert.rejects(cancelled, { name: 'AbortError' });
    finish[0]();
    await flush();
    assert.deepEqual(started, ['0', '1', '2', '3', 'next']);
    finish.slice(1).forEach(done => done());
    assert.equal((await outcomes)[0].status, 'rejected');
    assert.equal(await next, ok);
});

test('completed forecasts expire after five minutes, computing responses after eight seconds', async () => {
    let now = 0, count = 0, response = ok;
    const pool = createForecastRequests(async () => { count++; return response; }, () => now);
    await pool.load('a', signal());
    now = 299999;
    assert.equal(await pool.load('a', signal()), ok);
    assert.equal(count, 1);
    now = 300000;
    response = { status: 202, data: null };
    await pool.load('a', signal());
    now += 7999;
    await pool.load('a', signal());
    assert.equal(count, 2);
    now++;
    await pool.load('a', signal());
    assert.equal(count, 3);
});

test('the cache is bounded and server errors are retried instead of cached', async () => {
    let count = 0;
    const pool = createForecastRequests(async id => { count++; return id === 'error' ? { status: 503, data: null } : ok; });
    for (let i = 0; i < 65; i++) await pool.load(String(i), signal());
    await pool.load('64', signal());
    assert.equal(count, 65);
    await pool.load('0', signal());
    assert.equal(count, 66);
    await pool.load('error', signal());
    await pool.load('error', signal());
    assert.equal(count, 68);
});

test('forecast polling bounds fast retries and stops all work when hidden', async t => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    let now = 0, count = 0;
    const results = [];
    const pool = createForecastRequests(async () => { count++; return { status: 202, data: null }; }, () => now);
    const stop = pool.watch('a', result => results.push(result));
    await flush();
    for (let i = 0; i < 15; i++) { now += 8000; t.mock.timers.tick(8000); await flush(); }
    assert.equal(count, 16);
    now += 8000; t.mock.timers.tick(8000); await flush();
    assert.equal(count, 16);
    now += 292000; t.mock.timers.tick(292000); await flush();
    assert.equal(count, 17);
    stop();
    now += 300000; t.mock.timers.tick(300000); await flush();
    assert.equal(count, 17);
    assert.equal(results.length, 17);
});

test('an abandoned watcher does not deliver an in-flight result or restart polling', async t => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    let finish, count = 0;
    const pool = createForecastRequests(() => { count++; return new Promise(resolve => { finish = resolve; }); });
    const results = [];
    const stop = pool.watch('a', result => results.push(result));
    stop();
    finish(ok);
    await flush();
    t.mock.timers.tick(300000);
    await flush();
    assert.equal(count, 1);
    assert.deepEqual(results, []);
});
