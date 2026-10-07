import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';

const directory = mkdtempSync(join(tmpdir(), 'stratolink-terminator-'));
const source = readFileSync(new URL('../src/dashboard/components/maps/terminatorSource.ts', import.meta.url), 'utf8');
writeFileSync(join(directory, 'source.mjs'), ts.transpileModule(source.replace("'./terminatorRenderer'", "'./renderer.mjs'"), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText);
writeFileSync(join(directory, 'renderer.mjs'), `export class TerminatorRenderer {
  constructor(options) { this.options = options; }
  loadTile() { return Promise.resolve({ fallback: true, options: this.options }); }
  dispose() {}
}`);
const { TerminatorSource } = await import(pathToFileURL(join(directory, 'source.mjs')));
process.on('exit', () => rmSync(directory, { recursive: true, force: true }));

function fixture(t) {
  const workers = [];
  class Worker {
    sent = [];
    stopped = false;
    constructor() { workers.push(this); }
    postMessage(data) { this.sent.push(data); }
    terminate() { this.stopped = true; }
    receive(data) { this.onmessage({ data }); }
  }
  const replacements = { Worker, OffscreenCanvas: class {}, ImageData: class {
    constructor(data, width, height) { Object.assign(this, { data, width, height }); }
  }};
  const originals = Object.fromEntries(Object.keys(replacements).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  Object.assign(globalThis, replacements);
  t.after(() => {
    for (const [key, descriptor] of Object.entries(originals)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  });
  const source = new TerminatorSource({ tileSize: 1, basemap: 'light' });
  return { source, worker: workers[0] };
}

test('tile responses remain paired with their request when completed out of order', async t => {
  const { source, worker } = fixture(t);
  const a = source.loadTile({ z: 0, x: 0, y: 0 });
  const b = source.loadTile({ z: 1, x: 1, y: 0 });
  worker.receive({ id: 2, pixels: new Uint8Array([1, 2, 3, 4]).buffer });
  worker.receive({ id: 1, pixels: new Uint8Array([5, 6, 7, 8]).buffer });
  assert.deepEqual([...(await a).data], [5, 6, 7, 8]);
  assert.deepEqual([...(await b).data], [1, 2, 3, 4]);
  source.onRemove();
});

test('aborting one tile leaves other requests intact and ignores its late response', async t => {
  const { source, worker } = fixture(t);
  const controller = new AbortController();
  const a = source.loadTile({ z: 0, x: 0, y: 0 }, { signal: controller.signal });
  const rejected = assert.rejects(a, { name: 'AbortError' });
  const b = source.loadTile({ z: 1, x: 1, y: 0 });
  controller.abort();
  worker.receive({ id: 1, pixels: new Uint8Array(4).buffer });
  worker.receive({ id: 2, pixels: new Uint8Array(4).buffer });
  await rejected;
  assert.equal((await b).width, 1);
  source.onRemove();
});

test('source removal terminates its worker and settles outstanding tiles', async t => {
  const { source, worker } = fixture(t);
  const pending = source.loadTile({ z: 0, x: 0, y: 0 });
  const rejected = assert.rejects(pending, { name: 'AbortError' });
  source.onRemove();
  await rejected;
  assert.equal(worker.stopped, true);
  await assert.rejects(source.loadTile({ z: 0, x: 0, y: 0 }), { name: 'AbortError' });
});

test('a worker without WebGL falls back once using the current date and theme', async t => {
  const { source, worker } = fixture(t);
  source.setDate(new Date('2026-05-17T12:00:00Z'));
  source.setBasemap('dark');
  const pending = source.loadTile({ z: 0, x: 0, y: 0 });
  worker.receive({ id: 0, error: 'No worker WebGL' });
  const result = await pending;
  assert.equal(result.fallback, true);
  assert.equal(result.options.basemap, 'dark');
  assert.equal(result.options.date.toISOString(), '2026-05-17T12:00:00.000Z');
  assert.equal(worker.stopped, true);
  source.onRemove();
});
