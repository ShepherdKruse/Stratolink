import { docsCore } from './docs-core.mjs';
import { launchDocs } from './docs-launch.mjs';

const titles = {
  'getting-started': 'Getting started',
  architecture: 'System architecture',
  hardware: 'Hardware setup',
  dashboard: 'Dashboard guide',
  api: 'API reference',
  troubleshooting: 'Troubleshooting',
};
export const sections = Object.entries(docsCore).flatMap(([slug, content]) => [
  { slug, title: titles[slug], ...content },
  ...(slug === 'hardware' ? launchDocs : []),
]);
export const topicId = title => title.toLowerCase().replace(/[^a-z0-9]+/g, '-');
