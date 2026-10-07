import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { after, before, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { docsSearchApi, searchDocs } from './docsSearch.js';
import { embedText, searchAssets } from './docsSearchEmbedding.js';
import { sections, topicId } from '../content/docs.mjs';
import { contentHash, docsChunks } from './docsSearchContent.js';

let server;
let origin;
before(async () => {
  server = createServer(docsSearchApi);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
});
after(() => new Promise(resolve => server.close(resolve)));

test('the built index contains only current public doc sections and working anchors', async () => {
  const index = JSON.parse(await readFile(new URL('index.json', searchAssets), 'utf8'));
  assert.equal(index.fingerprint, contentHash(docsChunks(sections, topicId)));
  const anchors = new Set(sections.flatMap(section => section.topics.map(topic => `/docs/${section.slug}#${topicId(topic.title)}`)));
  for (const entry of index.entries) {
    assert(anchors.has(entry.url), entry.url);
    assert.equal(entry.embedding.length, 384);
    assert(Math.abs(Math.hypot(...entry.embedding) - 1) < 0.00001);
  }
});

test('sentence embeddings recognize meaning without matching vocabulary', async () => {
  const vectors = await Promise.all([
    embedText('The payload gets electricity from solar panels.'),
    embedText('Sunlight powers the onboard electronics.'),
    embedText('Sourdough bread rises before it goes in the oven.'),
  ]);
  const similarity = vector => vectors[0].reduce((sum, value, i) => sum + value * vector[i], 0);
  assert(similarity(vectors[1]) > similarity(vectors[2]) + .2);
});

test('questions retrieve the relevant instructions, including paraphrases', async () => {
  const cases = [
    ['How much helium do I need?', '/docs/balloon-prep#float-calculator'],
    ['How do I calculate how much gas to add?', '/docs/balloon-prep#float-calculator'],
    ['How can I see an earlier point in the flight?', '/docs/dashboard#flight-history'],
    ['Where can I connect it to the public radio network?', '/docs/getting-started#register-with-the-things-network'],
    ['How do I flash the firmware?', '/docs/hardware#build-and-flash'],
    ['What does HDOP mean?', '/docs/api#telemetry-fields'],
    ['Where do I find the AppKey?', '/docs/getting-started#register-with-the-things-network'],
  ];
  for (const [question, url] of cases) {
    const results = await searchDocs(question);
    assert(results.some(result => result.url === url), `${question}: ${results.map(result => result.url).join(', ')}`);
    assert.equal(new Set(results.map(result => result.url)).size, results.length);
  }
});

test('unsupported questions produce no invented answer or unrelated reference', async () => {
  for (const question of ['Give me a sourdough bread recipe', 'What is the capital of France?', 'How do I renew my passport?']) {
    assert.deepEqual(await searchDocs(question), [], question);
  }
});

test('the API validates method and query length before running inference', async () => {
  const post = await fetch(`${origin}/api/docs-search`, { method: 'POST' });
  assert.equal(post.status, 405);
  assert.equal(post.headers.get('allow'), 'GET');
  for (const query of ['', 'a', 'x'.repeat(301)]) {
    const response = await fetch(`${origin}/api/docs-search?q=${encodeURIComponent(query)}`);
    assert.equal(response.status, 400);
  }
});

test('the API returns cited excerpts without model vectors and does not cache questions publicly', async () => {
  const response = await fetch(`${origin}/api/docs-search?q=${encodeURIComponent('How can I see an earlier point in the flight?')}`);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('cache-control'), 'private, no-store');
  const data = await response.json();
  assert(data.results.length > 0);
  for (const result of data.results) {
    assert.match(result.url, /^\/docs\/[a-z-]+#[a-z0-9-]+$/);
    assert.equal(typeof result.excerpt, 'string');
    assert(!('embedding' in result));
    assert(!result.excerpt.includes('<script'));
  }
});
