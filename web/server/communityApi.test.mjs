import test from 'node:test';
import assert from 'node:assert/strict';
import { createCommunityApi, githubAccount, normalizeEui, verifyTTNDevice } from './communityApi.js';
const uid='00000000-0000-4000-8000-000000000001';
const bid='balloon-00000000-0000-4000-8000-000000000010';
const user={id:uid,identities:[{provider:'github',identity_data:{sub:'123456',user_name:'test-owner'}}]};
const balloon={id:bid,ownerId:uid,callsign:'Test',status:'planned',devEui:'1234567890ABCDEF',connections:[],connectionStatus:'pending'};
function fixture({authUser=user,owned=[balloon],verifyDevice,rate=true,rpcError=null,environment={}}={}) {
 const calls=[];
 let databaseCalls=0;
 const db={auth:{async getUser(){return {data:{user:authUser},error:null};}},async rpc(name,args){calls.push({name,args});return {data:name==='community_account'?owned:name==='community_rate_limit'?rate:balloon,error:rpcError};}};
 const api=createCommunityApi({createDb:()=>{databaseCalls++;return db;},environment:{SITE_URL:'https://stratolink.org',AUTH_ALLOWED_ORIGINS:'http://127.0.0.1:4173',COMMUNITY_REGISTRATION_ENABLED:'true',...environment},verifyDevice});
 const request=(path,method='GET',body,headers={})=>api(new Request(`http://localhost${path}`,{method,headers:{Authorization:'Bearer test-token-with-enough-characters',Origin:'https://stratolink.org','Content-Type':'application/json',...headers},...(body!==undefined?{body:typeof body==='string'?body:JSON.stringify(body)}:{})}));
 return {request,calls,get databaseCalls(){return databaseCalls;}};
}
test('registration and regional connection stay closed unless explicitly enabled, without database or TTN work',async()=>{
 for(const enabled of [undefined,'','false','TRUE','1',true]){
  let verified=false;
  const f=fixture({environment:{COMMUNITY_REGISTRATION_ENABLED:enabled},verifyDevice:()=>{verified=true;}});
  for(const [path,body] of [
   ['/api/balloons',{callsign:'Test',devEui:balloon.devEui}],
   [`/api/balloons/${bid}/connections`,{cluster:'eu1',applicationId:'my-app',deviceEui:balloon.devEui,apiKey:'TTN-key-private-never-stored'}],
  ]){
   const response=await f.request(path,'POST',body);
   assert.equal(response.status,503);
   assert.deepEqual(await response.json(),{error:'Registration unavailable'});
   assert.equal(response.headers.get('Cache-Control'),'no-store');
  }
  assert.equal(f.databaseCalls,0);
  assert.deepEqual(f.calls,[]);
  assert.equal(verified,false);
 }
});
test('disabled registration preserves account reads, owned status changes and request security checks',async()=>{
 const f=fixture({environment:{COMMUNITY_REGISTRATION_ENABLED:undefined}});
 assert.equal((await f.request('/api/account')).status,200);
 assert.equal((await f.request(`/api/balloons/${bid}`,'PATCH',{status:'landed'})).status,200);
 assert.ok(f.calls.some(call=>call.name==='update_community_balloon'));
 assert.equal((await f.request('/api/balloons','POST',{}, {Authorization:''})).status,401);
 assert.equal((await f.request('/api/balloons','POST',{}, {Origin:'https://evil.example'})).status,403);
 assert.equal((await f.request('/api/balloons','GET')).status,405);
});
test('GitHub identity is verified identity data, never editable metadata',()=>{
 assert.equal(githubAccount({id:uid,user_metadata:{user_name:'admin',provider_id:'1'}}),null);
 assert.equal(githubAccount({...user,is_anonymous:true}),null);
 assert.equal(githubAccount({...user,user_metadata:{user_name:'admin'}}).login,'test-owner');
 assert.equal(githubAccount({id:uid,identities:[{provider:'email',identity_data:{sub:'1',user_name:'admin'}}]}),null);
});
test('EUI normalization accepts usual notation and rejects blanks/zero',()=>{
 assert.equal(normalizeEui('12:34:56:78:90:ab:cd:ef'),'1234567890ABCDEF');
 for(const value of ['0000000000000000','1234','1234567890abcdeg',null,{}])assert.equal(normalizeEui(value),null);
});
test('anonymous, non-GitHub and wrong-origin mutations are denied before writes',async()=>{
 const f=fixture();
 assert.equal((await f.request('/api/balloons','POST',{callsign:'Test',devEui:balloon.devEui},{Authorization:''})).status,401);
 assert.equal((await f.request('/api/balloons','POST',{callsign:'Test',devEui:balloon.devEui},{Origin:'https://evil.example'})).status,403);
 assert.equal((await f.request('/api/balloons','POST',{callsign:'Test',devEui:balloon.devEui},{Origin:''})).status,403);
 assert.equal(f.calls.length,0);
 assert.equal((await fixture({authUser:{id:uid}}).request('/api/account')).status,403);
});
test('registration rejects owner/official injection and sends only server identity',async()=>{
 const f=fixture();
 assert.equal((await f.request('/api/balloons','POST',{callsign:'Test',devEui:balloon.devEui,ownerId:'other',official:true})).status,400);
 const r=await f.request('/api/balloons','POST',{callsign:'Test',devEui:balloon.devEui});
 assert.equal(r.status,201);
 assert.deepEqual(f.calls.find(c=>c.name==='register_community_balloon').args,{p_owner_id:uid,p_github_login:'test-owner',p_callsign:'Test',p_dev_eui:balloon.devEui});
});
test('foreign-owner changes and connections cannot probe TTN or mutate device',async()=>{
 let verified=false;
 const f=fixture({owned:[],verifyDevice:()=>{verified=true;}});
 assert.equal((await f.request(`/api/balloons/${bid}`,'PATCH',{status:'landed'})).status,404);
 assert.equal((await f.request(`/api/balloons/${bid}/connections`,'POST',{})).status,404);
 assert.equal(verified,false);
 assert.equal(f.calls.some(c=>c.name==='update_community_balloon'||c.name==='connect_community_radio'),false);
});
test('status and body allowlists reject escalation and oversized inputs',async()=>{
 const f=fixture();
 assert.equal((await f.request(`/api/balloons/${bid}`,'PATCH',{status:'official'})).status,400);
 assert.equal((await f.request(`/api/balloons/${bid}`,'PATCH',{status:'landed',ownerId:uid})).status,400);
 assert.equal((await f.request('/api/balloons','POST','x'.repeat(8193))).status,413);
 assert.equal((await f.request('/api/balloons','POST','{')).status,400);
 assert.equal((await f.request('/api/balloons','POST','{}',{'Content-Type':'text/plain'})).status,415);
});
test('database errors are redacted and request limits are enforced',async()=>{
 const limited=fixture({rate:false}); assert.equal((await limited.request('/api/balloons','POST',{})).status,429);
 const error=fixture({rpcError:{code:'XX000',message:'secret backend credentials'}});
 const r=await error.request('/api/account'); assert.equal(r.status,503);assert.doesNotMatch(await r.text(),/secret/);
});
test('successful connection stores only a hash and returns one-time credential at trusted URL',async()=>{
 const f=fixture({verifyDevice:async input=>({...input,deviceId:'my-device',region:'EU_863_870_TTN'})});
 const r=await f.request(`/api/balloons/${bid}/connections`,'POST',{cluster:'eu1',applicationId:'my-app',deviceEui:balloon.devEui,apiKey:'TTN-key-private-never-stored'});
 const body=await r.json();assert.equal(r.status,200);assert.equal(body.webhook.url,'https://stratolink.org/api/ttn-webhook');
 assert.equal(body.webhook.secret.length,43);
 const call=f.calls.find(c=>c.name==='connect_community_radio'); assert.match(call.args.p_token_hash,/^[a-f0-9]{64}$/);
 assert.doesNotMatch(JSON.stringify(call),/TTN-key|private-never-stored/);assert.equal(r.headers.get('Cache-Control'),'no-store');
});
test('legacy site URL supports existing deployments while rejecting unlisted request origins',async()=>{
 const f=fixture({environment:{SITE_URL:undefined,NEXT_PUBLIC_APP_URL:'https://stratolink.org'},verifyDevice:async input=>({...input,deviceId:'my-device',region:'EU_863_870_TTN'})});
 for(const origin of ['https://evil.example','https://stratolink.org.evil.example','https://preview.example']){
  assert.equal((await f.request(`/api/balloons/${bid}`,'PATCH',{status:'landed'},{Origin:origin,Host:'stratolink.org','X-Forwarded-Host':'stratolink.org'})).status,403);
 }
 assert.equal(f.databaseCalls,0);
 assert.equal((await f.request(`/api/balloons/${bid}`,'PATCH',{status:'landed'})).status,200);
 const response=await f.request(`/api/balloons/${bid}/connections`,'POST',{cluster:'eu1',applicationId:'my-app',deviceEui:balloon.devEui,apiKey:'TTN-key-private-never-stored'},{Host:'evil.example','X-Forwarded-Host':'evil.example'});
 assert.equal(response.status,200);
 assert.equal((await response.json()).webhook.url,'https://stratolink.org/api/ttn-webhook');
});
test('explicit site URL overrides legacy settings without enabling registration or trusting the request host',async()=>{
 const f=fixture({environment:{NEXT_PUBLIC_APP_URL:'https://old.example',COMMUNITY_REGISTRATION_ENABLED:undefined}});
 assert.equal((await f.request(`/api/balloons/${bid}`,'PATCH',{status:'landed'},{Origin:'https://old.example'})).status,403);
 assert.equal((await f.request(`/api/balloons/${bid}`,'PATCH',{status:'landed'})).status,200);
 assert.equal((await f.request('/api/balloons','POST',{callsign:'Test',devEui:balloon.devEui})).status,503);
 const missing=fixture({environment:{SITE_URL:undefined,NEXT_PUBLIC_APP_URL:undefined,AUTH_ALLOWED_ORIGINS:''}});
 assert.equal((await missing.request(`/api/balloons/${bid}`,'PATCH',{status:'landed'},{Host:'stratolink.org','X-Forwarded-Host':'stratolink.org'})).status,403);
 assert.equal(missing.databaseCalls,0);
});
test('legacy webhook URL still requires a bare HTTPS origin',async()=>{
 for(const site of ['http://stratolink.org','https://user:password@stratolink.org','https://stratolink.org/path','https://stratolink.org?query=1','https://stratolink.org#fragment']){
  const f=fixture({environment:{SITE_URL:undefined,NEXT_PUBLIC_APP_URL:site},verifyDevice:async input=>({...input,deviceId:'my-device',region:'EU_863_870_TTN'})});
  const response=await f.request(`/api/balloons/${bid}/connections`,'POST',{cluster:'eu1',applicationId:'my-app',deviceEui:balloon.devEui,apiKey:'TTN-key-private-never-stored'},{Origin:new URL(site).origin});
  assert.equal(response.status,503);
  assert.equal(f.calls.some(call=>call.name==='connect_community_radio'),false);
 }
});
test('TTN verification confines secret to fixed hosts, validates registry EUI and reads frequency plan',async()=>{
 const requests=[];
 const fetcher=async(url,options)=>{requests.push({url,options});return Response.json(url.includes('/ns/')?{ids:{device_id:'my-device',dev_eui:balloon.devEui,application_ids:{application_id:'my-app'}},frequency_plan_id:'EU_863_870_TTN'}:{end_devices:[{ids:{device_id:'my-device',dev_eui:balloon.devEui,application_ids:{application_id:'my-app'}}}]});};
 const result=await verifyTTNDevice({cluster:'eu1',applicationId:'my-app',deviceEui:balloon.devEui,apiKey:'NNSXS.long-private-api-key'},fetcher);
 assert.equal(result.deviceId,'my-device');assert.equal(result.region,'EU_863_870_TTN');
 for(const r of requests){assert.equal(new URL(r.url).host,'eu1.cloud.thethings.network');assert.equal(r.options.redirect,'error');assert.equal(r.options.headers.Authorization,'Bearer NNSXS.long-private-api-key');}
 await assert.rejects(()=>verifyTTNDevice({cluster:'evil.example',applicationId:'my-app',deviceEui:balloon.devEui,apiKey:'NNSXS.long-private-api-key'},fetcher));
});
test('TTN denial, foreign EUI and invalid remote responses do not establish ownership',async()=>{
 const input={cluster:'nam1',applicationId:'my-app',deviceEui:balloon.devEui,apiKey:'NNSXS.long-private-api-key'};
 await assert.rejects(()=>verifyTTNDevice(input,async()=>Response.json({},{status:403})),/permission/);
 await assert.rejects(()=>verifyTTNDevice(input,async()=>Response.json({end_devices:[]})),/not found/);
 await assert.rejects(()=>verifyTTNDevice(input,async()=>Response.json({end_devices:'wrong'})),/Invalid response/);
});

test('regional verification uses the central Identity Server and selected Network Server',async()=>{
 const ids={device_id:'my-device',dev_eui:balloon.devEui,application_ids:{application_id:'my-app'}};
 for(const cluster of ['nam1','au1']){
  const requests=[];
  const input={cluster,applicationId:'my-app',deviceEui:balloon.devEui,apiKey:'NNSXS.long-private-api-key'};
  const result=await verifyTTNDevice(input,async(url,options)=>{
   requests.push({url,options});
   return Response.json(url.includes('/ns/')?{ids,frequency_plan_id:'US_902_928_FSB_2'}:{end_devices:[{ids}]});
  });
  assert.equal(result.cluster,cluster);
  assert.equal(new URL(requests[0].url).host,'eu1.cloud.thethings.network');
  assert.equal(new URL(requests[1].url).host,`${cluster}.cloud.thethings.network`);
  for(const request of requests)assert.equal(request.options.method,undefined);
 }
});
test('device identity must match in both TTN registries before ownership is accepted',async()=>{
 const ids={device_id:'my-device',dev_eui:balloon.devEui,application_ids:{application_id:'my-app'}};
 const input={cluster:'nam1',applicationId:'my-app',deviceEui:balloon.devEui,apiKey:'NNSXS.long-private-api-key'};
 for(const changed of [{...ids,dev_eui:'FFFFFFFFFFFFFFFF'},{...ids,device_id:'other-device'},{...ids,application_ids:{application_id:'other-app'}}]){
  await assert.rejects(()=>verifyTTNDevice(input,async url=>Response.json(url.includes('/ns/')?{ids:changed,frequency_plan_id:'US_902_928_FSB_2'}:{end_devices:[{ids}]})),/registries disagree/);
 }
 let fetched=false;
 await assert.rejects(()=>verifyTTNDevice({...input,applicationId:undefined},async()=>{fetched=true;}),/Invalid network identity/);
 assert.equal(fetched,false);
});
