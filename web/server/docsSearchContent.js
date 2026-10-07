import { createHash } from 'node:crypto';

export function plainText(html) {
  const entities = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', deg: '°', times: '×', minus: '-', ge: '≥', le: '≤' };
  return html
    .replace(/<(script|style|svg|form|noscript|pre)\b[^>]*>[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<div class="docs-equation">[\s\S]*?<\/div>/g, ' ')
    .replace(/<[^>]*>/g, ' ')
    .replace(/&(#x[\da-f]+|#\d+|\w+);/gi, (match, entity) => {
      if (entity[0] !== '#') return entities[entity] ?? match;
      const point = entity[1] === 'x' ? parseInt(entity.slice(2), 16) : Number(entity.slice(1));
      return point <= 0x10ffff ? String.fromCodePoint(point) : ' ';
    })
    .replace(/\s+/g, ' ').trim();
}

export function docsChunks(sections, topicId) {
  return sections.flatMap(section => section.topics.flatMap(topic => {
    const text = plainText(topic.html);
    const openingParagraph = topic.html.match(/<p(?:\s[^>]*)?>([\s\S]*?)<\/p>/i)?.[1];
    const excerpt = plainText(openingParagraph || topic.html).slice(0, 320);
    const words = text.split(/\s+/);
    const chunks = [];
    for (let start = 0; start < words.length; start += 55) {
      const passage = words.slice(start, start + 75).join(' ');
      chunks.push({
        section: section.title,
        title: topic.title,
        url: `/docs/${section.slug}#${topicId(topic.title)}`,
        text: passage,
        excerpt,
      });
      if (start + 75 >= words.length) break;
    }
    return chunks;
  }));
}

export const contentHash = chunks => createHash('sha256').update(JSON.stringify(chunks)).digest('hex');
