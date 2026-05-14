import { chromium } from 'playwright';

const captureId = process.argv[2];
const targetUrl = process.argv[3];
const viewportWidth = parseInt(process.argv[4] || '1440');
const viewportHeight = parseInt(process.argv[5] || '900');

if (!captureId || !targetUrl) {
  console.error('Usage: node figma-capture.mjs <captureId> <url> [width] [height]');
  process.exit(1);
}

const endpoint = `https://mcp.figma.com/mcp/capture/${captureId}/submit`;

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: viewportWidth, height: viewportHeight },
  });
  const page = await context.newPage();

  // Strip CSP headers to allow script injection
  await page.route('**/*', async (route) => {
    try {
      const response = await route.fetch();
      const headers = { ...response.headers() };
      delete headers['content-security-policy'];
      delete headers['content-security-policy-report-only'];
      await route.fulfill({ response, headers });
    } catch (e) {
      await route.continue();
    }
  });

  console.log(`Navigating to ${targetUrl} (${viewportWidth}x${viewportHeight})...`);
  await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 30000 });

  // Extra wait for map tiles, animations, etc.
  await page.waitForTimeout(5000);

  // Inject the Figma capture script
  console.log('Injecting capture script...');
  const resp = await context.request.get('https://mcp.figma.com/mcp/html-to-design/capture.js');
  const scriptText = await resp.text();
  await page.evaluate((s) => {
    const el = document.createElement('script');
    el.textContent = s;
    document.head.appendChild(el);
  }, scriptText);

  await page.waitForTimeout(1000);

  // Execute the capture
  console.log(`Capturing with ID ${captureId}...`);
  const result = await page.evaluate(({ captureId, endpoint }) => {
    return window.figma.captureForDesign({ captureId, endpoint, selector: 'body' });
  }, { captureId, endpoint });

  console.log('Capture result:', JSON.stringify(result));

  await browser.close();
  console.log('Done!');
})();
