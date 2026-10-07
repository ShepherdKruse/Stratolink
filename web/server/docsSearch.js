import { readFile } from 'node:fs/promises';
import { embedText, searchAssets } from './docsSearchEmbedding.js';

const stopWords = new Set('a an and are as at be by can do does explain find for from get how i if in is it me mean meaning means much my need of on or our show tell that the their there these this to use using want was we what when where which why with you your'.split(' '));
const terms = text => text.toLowerCase().match(/[a-z0-9]+/g)?.filter(word => !stopWords.has(word)) ?? [];
let index;
let pending = 0;
let queue = Promise.resolve();
const cache = new Map();

export function rankPassages(query, embedding, entries) {
  const words = [...new Set(terms(query))];
  const passages = entries.map(entry => new Set(terms(`${entry.section} ${entry.title} ${entry.text}`)));
  const rareTerms = new Set(words.filter(word => passages.filter(passage => passage.has(word)).length < entries.length * .1));
  const ranked = entries.map((entry, index) => {
    const semantic = entry.embedding.reduce((sum, value, i) => sum + value * embedding[i], 0);
    const haystack = passages[index];
    const lexical = words.length ? words.filter(word => haystack.has(word)).length / words.length : 0;
    const exact = lexical === 1 && words.some(word => rareTerms.has(word));
    return { entry, semantic, exact, score: semantic + .20 * lexical };
  }).sort((a, b) => b.score - a.score);
  const seen = new Set();
  return ranked.filter(result => {
    if ((!result.exact && result.semantic < .22) || result.score < .31 || seen.has(result.entry.url)) return false;
    seen.add(result.entry.url);
    return true;
  }).slice(0, 5).map(({ entry }) => ({
    section: entry.section, title: entry.title, url: entry.url,
    excerpt: entry.excerpt.length > 300 ? `${entry.excerpt.slice(0, 300).replace(/\s+\S*$/, '')}…` : entry.excerpt,
  }));
}

export async function searchDocs(query) {
  const key = query.toLowerCase();
  if (cache.has(key)) return cache.get(key);
  index ??= readFile(new URL('index.json', searchAssets), 'utf8').then(JSON.parse).catch(error => { index = undefined; throw error; });
  const [{ entries }, embedding] = await Promise.all([index, embedText(query)]);
  const results = rankPassages(query, embedding, entries);
  if (cache.size >= 100) cache.delete(cache.keys().next().value);
  cache.set(key, results);
  return results;
}

export async function docsSearchApi(request, response) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  response.setHeader('Cache-Control', 'private, no-store');
  response.setHeader('X-Content-Type-Options', 'nosniff');
  const send = (status, body) => { response.statusCode = status; response.end(JSON.stringify(body)); };
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET');
    return send(405, { error: 'Use GET to search docs.' });
  }
  const query = new URL(request.url, 'http://localhost').searchParams.get('q')?.trim() ?? '';
  if (query.length < 2 || query.length > 300) return send(400, { error: 'Enter between 2 and 300 characters.' });
  if (pending >= 4) {
    response.setHeader('Retry-After', '2');
    return send(503, { error: 'Search is busy. Try again in a moment.' });
  }
  pending++;
  const result = queue.then(() => searchDocs(query));
  queue = result.catch(() => {});
  try { send(200, { query, results: await result }); }
  catch (error) {
    console.error('Docs search failed:', error.message);
    send(503, { error: 'Search is unavailable. Browse the sections below.' });
  } finally { pending--; }
}
