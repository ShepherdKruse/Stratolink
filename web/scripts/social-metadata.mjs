export const siteDescription = 'Open-source, solar-powered balloon payloads for collecting and sharing data from the stratosphere. Build your own, follow our flights, and join the network.';

const launchImage = {
  src: '/assets/launch/source.jpg',
  width: 2560,
  height: 1440,
  alt: 'A Stratolink balloon and its payload above the San Francisco skyline and clouds.',
};
const escape = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const absolute = path => new URL(path, 'https://stratolink.org').href;

export function socialMetadata({ title, path, description = siteDescription, image = launchImage, type = 'website' }) {
  const imageUrl = escape(absolute(image.src));
  const imageType = image.src.endsWith('.png') ? 'image/png' : image.src.endsWith('.webp') ? 'image/webp' : 'image/jpeg';
  return `  <meta name="description" content="${escape(description)}">
  <link rel="canonical" href="${escape(absolute(path))}">
  <meta property="og:site_name" content="Stratolink">
  <meta property="og:type" content="${escape(type)}">
  <meta property="og:title" content="${escape(title)}">
  <meta property="og:description" content="${escape(description)}">
  <meta property="og:url" content="${escape(absolute(path))}">
  <meta property="og:image" content="${imageUrl}">
  <meta property="og:image:type" content="${imageType}">
  <meta property="og:image:width" content="${image.width}">
  <meta property="og:image:height" content="${image.height}">
  <meta property="og:image:alt" content="${escape(image.alt)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${escape(title)}">
  <meta name="twitter:description" content="${escape(description)}">
  <meta name="twitter:image" content="${imageUrl}">
  <meta name="twitter:image:alt" content="${escape(image.alt)}">`;
}
