import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { Tokenizer } from '@huggingface/tokenizers';
import { InferenceSession, Tensor } from 'onnxruntime-node';

export const searchAssets = new URL('./search-assets/', import.meta.url);
let encoder;

async function loadEncoder() {
  const [definition, configuration, session] = await Promise.all([
    readFile(new URL('model/tokenizer.json', searchAssets), 'utf8').then(JSON.parse),
    readFile(new URL('model/tokenizer_config.json', searchAssets), 'utf8').then(JSON.parse),
    InferenceSession.create(fileURLToPath(new URL('model/onnx/model_quantized.onnx', searchAssets)), {
      executionProviders: ['cpu'], intraOpNumThreads: 1, interOpNumThreads: 1,
    }),
  ]);
  return { tokenizer: new Tokenizer(definition, configuration), session };
}

export async function embedText(text) {
  encoder ??= loadEncoder().catch(error => { encoder = undefined; throw error; });
  const { tokenizer, session } = await encoder;
  const encoded = tokenizer.encode(text);
  const ids = encoded.ids.length > 256 ? [...encoded.ids.slice(0, 255), 102] : encoded.ids;
  const tensor = values => new Tensor('int64', BigInt64Array.from(values, BigInt), [1, ids.length]);
  const output = await session.run({
    input_ids: tensor(ids),
    attention_mask: tensor(ids.map(() => 1)),
    token_type_ids: tensor(ids.map(() => 0)),
  });
  const hidden = output.last_hidden_state;
  const dimensions = hidden.dims[2];
  const vector = Array(dimensions).fill(0);
  for (let token = 0; token < ids.length; token++) {
    for (let dim = 0; dim < dimensions; dim++) vector[dim] += hidden.data[token * dimensions + dim] / ids.length;
  }
  const magnitude = Math.hypot(...vector);
  return vector.map(value => value / magnitude);
}
