import { setTimeout } from 'node:timers/promises';

const expected = process.argv[2];
if (!/^[a-f0-9]{40}$/.test(expected || '')) throw new Error('Pass the deployed commit SHA.');

let failure;
for (let attempt = 0; attempt < 18; attempt++) {
  try {
    const get = async path => {
      const response = await fetch(`https://stratolink.org${path}?release_check=${Date.now()}`, {
        cache: 'no-store', signal: AbortSignal.timeout(15000),
      });
      if (!response.ok) throw new Error(`${path} returned ${response.status}`);
      return response.text();
    };
    const [identity, home, blog, dashboard] = await Promise.all([
      get('/release.json'), get('/'), get('/blog'), get('/dashboard'),
    ]);
    const release = JSON.parse(identity);
    if (release.site !== 'stratolink' || release.commit !== expected) {
      throw new Error(`The domain does not serve commit ${expected}. Check the Vercel Production assignment.`);
    }
    if (!home.includes('class="launch"') || !blog.includes('class="blog-main"') || !dashboard.includes('Dashboard - Stratolink')) {
      throw new Error('Production routes do not match the current Stratolink website.');
    }
    console.log(`stratolink.org serves ${expected}; homepage, blog and dashboard verified.`);
    process.exit(0);
  } catch (error) {
    failure = error;
    if (attempt < 17) await setTimeout(10000);
  }
}
console.error(failure.message);
process.exitCode = 1;
