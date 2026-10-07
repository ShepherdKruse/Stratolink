import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer, request as httpRequest } from 'node:http';
import { once } from 'node:events';
import { nodeHandler } from './httpAdapter.js';

async function serverFor(handler, options, run) {
  const server = createServer(nodeHandler(handler, options));
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  try { await run(`http://127.0.0.1:${server.address().port}`); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}

test('Node adapter preserves the exact body, headers, cookies and response status', async () => {
  await serverFor(async request => {
    assert.equal(request.headers.get('authorization'), 'Bearer example');
    assert.equal(await request.text(), 'hello\nworld');
    const response = new Response('created', { status: 201 });
    response.headers.append('set-cookie', 'first=value; HttpOnly');
    response.headers.append('set-cookie', 'second=value; HttpOnly');
    return response;
  }, {}, async base => {
    const result = await fetch(base, { method: 'POST', headers: { authorization: 'Bearer example' }, body: 'hello\nworld' });
    assert.equal(result.status, 201);
    assert.equal(await result.text(), 'created');
    assert.equal(result.headers.getSetCookie().length, 2);
  });
});

test('Node adapter caps declared and chunked bodies without exposing thrown errors', async () => {
  let calls = 0;
  await serverFor(async request => { calls++; await request.text(); return new Response('unexpected'); }, { maxBodyBytes: 100 }, async base => {
    const oversized = await fetch(base, { method: 'POST', body: 'a'.repeat(101) });
    assert.equal(oversized.status, 413);
    assert.equal(calls, 0);
    const chunked = await new Promise((resolve, reject) => {
      const req = httpRequest(base, { method: 'POST', headers: { 'transfer-encoding': 'chunked' } }, res => {
        let text = ''; res.setEncoding('utf8'); res.on('data', data => text += data); res.on('end', () => resolve({ status: res.statusCode, text }));
      });
      req.on('error', reject);
      req.write('a'.repeat(60)); req.end('b'.repeat(60));
    });
    assert.equal(chunked.status, 413);
    assert.ok(!chunked.text.includes('Error:'));
    assert.equal(calls, 1);
  });
  await serverFor(async () => { throw new Error('private database password'); }, {}, async base => {
    const result = await fetch(base);
    assert.equal(result.status, 500);
    assert.ok(!(await result.text()).includes('password'));
  });
});
