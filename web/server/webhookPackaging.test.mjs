import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

test('compiled webhook imports emitted JavaScript and rejects unsigned requests without database access', async () => {
  const root = fileURLToPath(new URL('../', import.meta.url));
  const configPath = ts.findConfigFile(join(root, 'api'), ts.sys.fileExists);
  const config = ts.readConfigFile(configPath, ts.sys.readFile);
  assert.equal(config.error, undefined);
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, join(root, 'api'));
  const target = await mkdtemp(join(tmpdir(), 'stratolink-webhook-compiled-'));
  try {
    const program = ts.createProgram([join(root, 'api/ttn-webhook.ts')], {
      ...parsed.options, noEmit: false, rootDir: root, outDir: target,
    });
    const diagnostics = ts.getPreEmitDiagnostics(program);
    assert.equal(diagnostics.length, 0, ts.formatDiagnostics(diagnostics, {
      getCanonicalFileName: name => name, getCurrentDirectory: () => root, getNewLine: () => '\n',
    }));
    assert.equal(program.emit().emitSkipped, false);
    await writeFile(join(target, 'package.json'), '{"type":"module"}');
    await symlink(join(root, 'node_modules'), join(target, 'node_modules'), 'dir');
    const { default: handler } = await import(pathToFileURL(join(target, 'api/ttn-webhook.js')).href);
    const address = 'https://stratolink.org/api/ttn-webhook';
    const get = await handler.fetch(new Request(address));
    assert.equal(get.status, 405);
    assert.equal(get.headers.get('Allow'), 'POST');
    const unsigned = await handler.fetch(new Request(address, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }));
    assert.equal(unsigned.status, 401);
    assert.equal(unsigned.headers.get('WWW-Authenticate'), 'Bearer');
    assert.deepEqual(await unsigned.json(), { error: 'Unauthorized' });
  } finally { await rm(target, { recursive: true, force: true }); }
});
