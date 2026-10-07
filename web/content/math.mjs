import katex from 'katex';

export const math = tex => `<div class="docs-equation">${katex.renderToString(tex, { displayMode: true, throwOnError: true, output: 'htmlAndMathml', trust: false })}</div>`;
