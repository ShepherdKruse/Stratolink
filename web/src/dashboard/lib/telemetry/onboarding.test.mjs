import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
import { onboardingEntry, onboardingDashboardPath, validClaimToken } from '../community/onboarding.ts';
import { storedReturnState } from '../community/returnDevice.ts';

const token = 'A'.repeat(43);

test('printed QR routes retain device context and only accept the claim token shape', () => {
    assert.deepEqual(onboardingEntry(`https://stratolink.org/activate/stratolink-3#k=${token}`), { mode:'activate', direct:true, deviceId:'stratolink-3', claimToken:token });
    assert.deepEqual(onboardingEntry(`https://stratolink.org/activate/stratolink-3?k=${token}`), { mode:'activate', direct:true, deviceId:'stratolink-3', claimToken:token });
    assert.deepEqual(onboardingEntry('https://stratolink.org/claim'), { mode:'reserve', direct:true });
    for (const path of ['/activate/stratolink-3?k=123456', '/activate/stratolink-3?k=%3Cscript%3E']) {
        const entry = onboardingEntry(`https://stratolink.org${path}`);
        assert.equal(entry.deviceId, 'stratolink-3');
        assert.equal(entry.claimToken, undefined);
    }
    for (const id of ['%2F%2Fevil.example', '%3Cscript%3E', '%E0%A4', 'a'.repeat(81)]) {
        assert.equal(onboardingEntry(`https://stratolink.org/activate/${id}?k=${token}`).deviceId, undefined);
    }
    assert.equal(onboardingEntry('https://stratolink.org/activate/a/b'), null);
    assert.equal(onboardingEntry('https://stratolink.org/dashboard?onboarding=https://evil.example'), null);
    assert.equal(validClaimToken('123456'), false);
});

test('conflicting or duplicate credentials retain the payload but never choose a proof', () => {
    for (const suffix of [
        `?k=${token}#k=${'B'.repeat(43)}`,
        `?k=${token}#k=${token}`,
        `?k=${token}&k=${token}`,
        `#k=${token}&k=${token}`,
        `?k=#k=${token}`,
        `#k=${token}&%6B=bad`,
    ]) {
        assert.deepEqual(onboardingEntry(`https://stratolink.org/activate/stratolink-3${suffix}`), { mode:'activate', direct:true, deviceId:'stratolink-3' });
    }
});

test('OAuth state contains only a bounded mode and device, never raw credentials or a destination', () => {
    const record = { device:'stratolink-3', onboarding:'activate', createdAt:1000, claimToken:token, next:'https://evil.example' };
    assert.deepEqual(storedReturnState(JSON.stringify(record), 1100), { device:'stratolink-3', onboarding:'activate', createdAt:1000 });
    assert.deepEqual(storedReturnState(JSON.stringify({ onboarding:'reserve', createdAt:1000 }), 1100), { onboarding:'reserve', createdAt:1000 });
    assert.equal(onboardingDashboardPath('activate', 'stratolink-3'), '/dashboard?device=stratolink-3&onboarding=activate');
    assert.equal(onboardingDashboardPath(null, '//evil.example'), '/dashboard');
    for (const record of [null, {}, {onboarding:'https://evil.example',createdAt:1000}, {onboarding:'activate',createdAt:1200}, {onboarding:'activate',createdAt:1000-16*60_000}]) {
        assert.equal(storedReturnState(JSON.stringify(record), 1100), null);
    }
});

async function activationModule() {
    // Isolate browser module state between tests without a real auth or database request.
    const source = (await readFile(new URL('../community/activation.ts', import.meta.url), 'utf8'))
        .replace("from './onboarding'", `from '${new URL('../community/onboarding.ts', import.meta.url).href}'`);
    const js = ts.transpileModule(source, { compilerOptions: { target:ts.ScriptTarget.ES2022, module:ts.ModuleKind.ESNext } }).outputText;
    return import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}#${crypto.randomUUID()}`);
}

test('QR boot scrubs secrets immediately, sends once, and serializes cancellation after pending cookie write', async t => {
    const calls = [];
    let release;
    const location = { href:`https://stratolink.org/activate/stratolink-3#k=${token}` };
    t.mock.method(globalThis, 'fetch', async (_url, options) => {
        calls.push(options);
        if (options.method === 'POST') await new Promise(resolve => { release = resolve; });
        return Response.json({ intent: options.method === 'DELETE' ? null : {deviceId:'stratolink-3',requiresProof:false,expiresAt:'2026-10-08T00:00:00Z'} });
    });
    Object.defineProperty(globalThis, 'location', { configurable:true, value:location });
    Object.defineProperty(globalThis, 'history', { configurable:true, value:{state:null,replaceState(_state,_title,path) { location.href = new URL(path, location.href).href; }} });
    t.after(() => { delete globalThis.location; delete globalThis.history; });
    const client = await activationModule();
    const boot = client.initializeOnboarding();
    assert.equal(location.href, 'https://stratolink.org/dashboard?onboarding=activate');
    assert.equal(client.initializeOnboarding(), boot);
    const cancel = client.clearActivation();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(calls.map(call => call.method), ['POST']);
    release();
    await Promise.all([boot,cancel]);
    assert.deepEqual(calls.map(call => call.method), ['POST','DELETE']);
    assert.equal(calls[0].credentials, 'same-origin');
    assert.deepEqual(JSON.parse(calls[0].body), {deviceId:'stratolink-3',claimToken:token});
});

test('ordinary dashboard does not resume an abandoned cookie; explicit refresh does', async t => {
    const calls = [];
    t.mock.method(globalThis, 'fetch', async (_url, options) => { calls.push(options); return Response.json({intent:null}); });
    Object.defineProperty(globalThis, 'location', { configurable:true, writable:true, value:{href:'https://stratolink.org/dashboard'} });
    t.after(() => { delete globalThis.location; });
    const ordinary = await activationModule();
    assert.deepEqual(await ordinary.initializeOnboarding(), {mode:null,intent:null});
    assert.equal(calls.length, 0);
    globalThis.location.href = 'https://stratolink.org/dashboard?onboarding=activate';
    const refresh = await activationModule();
    assert.deepEqual(await refresh.initializeOnboarding(), {mode:'activate',intent:null});
    assert.deepEqual(calls.map(call => call.method), ['GET']);
});

test('legacy and ambiguous URLs scrub query and fragment before the first request', async t => {
    const calls = [];
    const location = {href:'https://stratolink.org/dashboard'};
    Object.defineProperty(globalThis, 'location', {configurable:true,value:location});
    Object.defineProperty(globalThis, 'history', {configurable:true,value:{state:null,replaceState(_state,_title,path) { location.href = new URL(path,location.href).href; }}});
    t.after(() => { delete globalThis.location; delete globalThis.history; });
    t.mock.method(globalThis, 'fetch', async (_url, options) => {
        assert.equal(location.href, 'https://stratolink.org/dashboard?onboarding=activate');
        calls.push(JSON.parse(options.body));
        return Response.json({intent:null});
    });
    for (const suffix of [`?k=${token}`, `?k=${token}#k=${'B'.repeat(43)}`]) {
        location.href = `https://stratolink.org/activate/stratolink-3${suffix}`;
        const client = await activationModule();
        await client.initializeOnboarding();
    }
    assert.deepEqual(calls, [{deviceId:'stratolink-3',claimToken:token}, {deviceId:'stratolink-3'}]);
});
