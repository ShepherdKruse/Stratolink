import { createHash } from 'node:crypto';
import { copyFile, mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { sections, topicId } from '../content/docs.mjs';
import { docsChunks, contentHash } from '../server/docsSearchContent.js';
import { embedText, searchAssets } from '../server/docsSearchEmbedding.js';

const manifest = JSON.parse(await readFile(new URL('../server/docsSearchModel.json', import.meta.url), 'utf8'));
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
await mkdir(new URL('model/onnx/', searchAssets), { recursive: true });
await copyFile(new URL('../server/docsSearchModel.LICENSE', import.meta.url), new URL('model/LICENSE', searchAssets));
await writeFile(new URL('model/NOTICE', searchAssets), `${manifest.model}\nhttps://huggingface.co/${manifest.model}\nRevision ${manifest.revision}\nApache License 2.0\n`);
for (const [file, checksum] of Object.entries(manifest.files)) {
  const target = new URL(`model/${file}`, searchAssets);
  const existing = await readFile(target).catch(error => { if (error.code !== 'ENOENT') throw error; });
  if (existing && sha256(existing) === checksum) continue;
  const url = `https://huggingface.co/${manifest.model}/resolve/${manifest.revision}/${file}`;
  const response = await fetch(url, { signal: AbortSignal.timeout(120_000) });
  if (!response.ok) throw new Error(`Search model download failed: ${response.status} (${file})`);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (sha256(bytes) !== checksum) throw new Error(`Search model checksum does not match: ${file}`);
  await writeFile(target, bytes);
}

const chunks = docsChunks(sections, topicId);
const fingerprint = contentHash(chunks);
const target = new URL('index.json', searchAssets);
const previous = await readFile(target, 'utf8').then(JSON.parse).catch(error => { if (error.code !== 'ENOENT') throw error; });
if (previous?.fingerprint === fingerprint && previous.modelRevision === manifest.revision) {
  console.log(`Docs search index is current (${chunks.length} passages).`);
} else {
  const entries = [];
  for (const chunk of chunks) {
    const embedding = await embedText(`${chunk.section}. ${chunk.title}. ${chunk.text}`);
    entries.push({ ...chunk, embedding: embedding.map(value => Number(value.toFixed(7))) });
  }
  const temporary = new URL('index.json.tmp', searchAssets);
  await writeFile(temporary, JSON.stringify({ fingerprint, modelRevision: manifest.revision, entries }));
  await rename(temporary, target);
  console.log(`Built semantic docs search index (${entries.length} passages).`);
}
