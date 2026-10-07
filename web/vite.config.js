import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import { writeBlogPages } from './scripts/blog-pages.mjs';
import { posts } from './content/blog.mjs';
import { writeDocsPages } from './scripts/docs-pages.mjs';
import { sections } from './content/docs.mjs';
import { writeHomeInserts } from './scripts/home-inserts.mjs';
import { publicBuildDefines } from './scripts/public-config.mjs';
import { dashboardApi } from './server/dashboardApi.js';
import { forecastApi } from './server/forecastApi.js';
import { ttnWebhook } from './server/ttnWebhook.ts';
import communityApi from './server/communityApi.js';
import { nodeHandler } from './server/httpAdapter.js';

const communityHandler = nodeHandler(communityApi);
const ttnHandler = nodeHandler(ttnWebhook);
import { docsSearchApi } from './server/docsSearch.js';


function dashboardRoute(server) {
  server.middlewares.use((request, response, next) => {
    if (/^\/api\/docs-search(\?|$)/.test(request.url ?? "")) return void docsSearchApi(request, response);
    if (/^\/docs\/float-calculator\/?(\?|$)/.test(request.url ?? "")) {
      response.statusCode = 308;
      response.setHeader('Location', '/docs/balloon-prep#float-calculator');
      return response.end();
    }
    if (/^\/api\/telemetry(\?|$)/.test(request.url ?? "")) return void dashboardApi(request, response);
    if (/^\/api\/forecast(\?|$)/.test(request.url ?? "")) return void forecastApi(request, response);
    if (/^\/api\/ttn-webhook(\?|$)/.test(request.url ?? "")) return void ttnHandler(request, response);
    if (/^\/api\/(account|balloons|activation|staff)(\/|\?|$)/.test(request.url ?? "")) return void communityHandler(request, response);
    const legacyPath = new URL(request.url ?? '/', 'http://localhost').pathname;
    if (/^\/admin(\/|$)/.test(legacyPath) || /^\/dashboard-v2(\/|$)/.test(legacyPath)) {
      response.statusCode = legacyPath.startsWith('/dashboard-v2') ? 308 : 307;
      response.setHeader('Location', '/dashboard');
      return response.end();
    }
    if (/^\/(activate(?:\/[^/]+)?|claim)\/?$/.test(legacyPath)) {
      response.setHeader('Referrer-Policy', 'no-referrer');
      response.setHeader('Cache-Control', 'no-store');
      request.url = '/dashboard/index.html';
    }
    const legacyFlight = request.url?.match(/^\/flights(\/baja-run)?\/?(\?.*)?$/);
    if (legacyFlight) {
      response.statusCode = 308;
      response.setHeader('Location', `/blog${legacyFlight[1] || ''}${legacyFlight[2] || ''}`);
      return response.end();
    }
    request.url = request.url?.replace(/^\/dashboard\/?(\?|$)/, '/dashboard/index.html$1');
    request.url = request.url?.replace(/^\/blog\/?(\?|$)/, '/blog/index.html$1');
    request.url = request.url?.replace(/^\/docs\/?(\?|$)/, '/docs/index.html$1');
    const doc = request.url?.match(/^\/docs\/([^/?]+)\/?(\?.*)?$/);
    if (doc && doc[1] !== 'index.html') {
      if (!sections.some(section => section.slug === doc[1])) { response.statusCode = 404; return response.end('Document not found'); }
      request.url = `/docs/pages/${doc[1]}.html${doc[2] || ''}`;
    }
    const article = request.url?.match(/^\/blog\/([^/?]+)\/?(\?.*)?$/);
    if (article && article[1] !== 'index.html') {
      if (!posts.some(post => post.slug === article[1])) { response.statusCode = 404; return response.end('Article not found'); }
      request.url = `/blog/posts/${article[1]}.html${article[2] || ''}`;
    }
    next();
  });
}

export default defineConfig(({ mode }) => {
  writeHomeInserts();
  const env = loadEnv(mode, process.cwd(), '');
  for (const name of ['SUPABASE_URL', 'SUPABASE_SERVER_KEY', 'SUPABASE_SERVICE_ROLE_KEY', 'NEXT_PUBLIC_SUPABASE_URL', 'TTN_WEBHOOK_SECRET', 'BLOB_READ_WRITE_TOKEN', 'SITE_URL', 'NEXT_PUBLIC_APP_URL', 'AUTH_ALLOWED_ORIGINS', 'COMMUNITY_REGISTRATION_ENABLED', 'PAYLOAD_CLAIM_COOKIE_SECRET', 'PAYLOAD_STAFF_USER_IDS']) {
    if (!process.env[name] && env[name]) process.env[name] = env[name];
  }
  return {
    plugins: [{ name: 'dashboard-route', configureServer: dashboardRoute, configurePreviewServer: dashboardRoute }],
    resolve: { alias: { '@': fileURLToPath(new URL('./src/dashboard', import.meta.url)) } },
    envPrefix: [],
    define: publicBuildDefines(process.env, env),
    build: {
      rolldownOptions: {
        input: {
          ...writeBlogPages(),
          ...writeDocsPages(),
          home: fileURLToPath(new URL('./index.html', import.meta.url)),
          blog: fileURLToPath(new URL('./blog/index.html', import.meta.url)),
          dashboard: fileURLToPath(new URL('./dashboard/index.html', import.meta.url)),
        },
      },
    },
  };
});
