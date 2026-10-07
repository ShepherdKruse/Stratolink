import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac, randomBytes } from 'node:crypto';
import { writeClaimIntent, readClaimIntent, clearClaimIntent, publicClaimIntent } from './payloadClaim.js';

const environment = { PAYLOAD_CLAIM_COOKIE_SECRET:randomBytes(32).toString('base64url') };
const now = 1_800_000_000_000;
const input = {deviceId:'stratolink-3',tokenHash:'a'.repeat(64),origin:'https://stratolink.org'};
const name = 'stratolink-payload-claim';
const request = cookie => new Request('https://stratolink.org/api/activation/claim', {headers:{cookie}});
const cookieFrom = response => response.headers.get('set-cookie').split(';')[0];
const issue = (overrides = {}) => writeClaimIntent(Response.json({}), {...input,...overrides}, environment, now);
function signedCookie(value) {
    const encoded = Buffer.from(JSON.stringify(value)).toString('base64url');
    const mac = createHmac('sha256',Buffer.from(environment.PAYLOAD_CLAIM_COOKIE_SECRET,'base64url')).update(`payload-claim:v1:${encoded}`).digest('base64url');
    return `${name}=${encoded}.${mac}`;
}

test('claim cookie scopes and public context omit proof and authorization data', () => {
    const response = issue();
    const header = response.headers.get('set-cookie');
    for (const flag of ['Path=/api/activation','HttpOnly','SameSite=Lax','Max-Age=1800','Secure']) assert.ok(header.includes(flag));
    assert.equal(/Domain=/i.test(header), false);
    const intent = readClaimIntent(request(cookieFrom(response)), environment, now+1000);
    assert.equal(intent.deviceId, input.deviceId);
    assert.equal(intent.origin, input.origin);
    assert.deepEqual(publicClaimIntent(intent), {deviceId:'stratolink-3',requiresProof:false,expiresAt:new Date(now+1800_000).toISOString()});
    assert.deepEqual(publicClaimIntent({...intent,tokenHash:null}), {deviceId:'stratolink-3',requiresProof:true,expiresAt:new Date(now+1800_000).toISOString()});
    assert.equal(JSON.stringify(publicClaimIntent(intent)).includes(input.tokenHash), false);
    assert.equal(publicClaimIntent(null), null);
});

test('cookie edits, duplicate names, malformed values and a rotated signing key fail closed', () => {
    const cookie = cookieFrom(issue());
    const value = cookie.split('=')[1].split('.')[0];
    const parsed = JSON.parse(Buffer.from(value,'base64url').toString());
    const changed = Buffer.from(JSON.stringify({...parsed,deviceId:'someone-else'})).toString('base64url');
    for (const candidate of [cookie.replace(value,changed), `${cookie}; ${cookie}`, `${cookie}.extra`, `${name}=broken`, `${name}=${'x'.repeat(1501)}`, `${name}=`]) {
        assert.equal(readClaimIntent(request(candidate),environment,now),null);
    }
    assert.equal(readClaimIntent(request(cookie),{PAYLOAD_CLAIM_COOKIE_SECRET:randomBytes(32).toString('base64url')},now),null);
    assert.equal(readClaimIntent(request(cookie),{},now),null);
});

test('signed but malformed or stale claim records cannot extend their lifetime', () => {
    const valid = {v:1,...input,expires:now+1800_000};
    for (const patch of [{v:2},{expires:now},{expires:now-1},{expires:now+1800_001},{expires:'tomorrow'},{tokenHash:'bad'},{deviceId:'../admin'},{origin:'https://stratolink.org/path'},{origin:'null'}]) {
        assert.equal(readClaimIntent(request(signedCookie({...valid,...patch})),environment,now),null);
    }
    const issued = request(cookieFrom(issue()));
    assert.notEqual(readClaimIntent(issued,environment,now+1799_999),null);
    assert.equal(readClaimIntent(issued,environment,now+1800_000),null);
});

test('cancel expires exactly the same host and path cookie; production requires Secure', () => {
    const cancelled = clearClaimIntent(Response.json({}),input.origin).headers.get('set-cookie');
    for (const flag of [`${name}=;`,'Path=/api/activation','HttpOnly','SameSite=Lax','Max-Age=0','Secure']) assert.ok(cancelled.includes(flag));
    assert.equal(/Domain=/i.test(cancelled),false);
    assert.equal(issue({origin:'http://127.0.0.1:4174'}).headers.get('set-cookie').includes('; Secure'),false);
    assert.throws(() => writeClaimIntent(Response.json({}),input,{PAYLOAD_CLAIM_COOKIE_SECRET:'short'},now));
});
