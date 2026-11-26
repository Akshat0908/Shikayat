import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {once} from 'node:events';

const script=new URL('../scripts/simulate-flagsmith.mjs',import.meta.url).pathname;
function run(args,env={}){
 return new Promise((resolve,reject)=>{
  const child=spawn(process.execPath,[script,...args],{env:{...process.env,...env}});
  let out='',err='';child.stdout.on('data',b=>out+=b);child.stderr.on('data',b=>err+=b);
  child.on('error',reject);child.on('close',code=>resolve({code,out,err}));
 });
}

test('simulation requires explicit acknowledgement and a separate environment',async()=>{
 const a=await run([]);assert.equal(a.code,2);assert.match(a.err,/Refusing to send/);
 const b=await run(['--ack-synthetic'],{FLAGSMITH_SYNTHETIC_ENVIRONMENT_ID:'same',FLAGSMITH_ENVIRONMENT_ID:'same'});
 assert.equal(b.code,2);assert.match(b.err,/dedicated test environment/);
});

test('official SDK sends synthetic exposures and case-start events to the configured service',async()=>{
 const events=[];
 const server=http.createServer(async(req,res)=>{
  let body='';for await(const chunk of req)body+=chunk;
  res.setHeader('content-type','application/json');
  if(req.url.startsWith('/api/v1/identities/')){
   res.end(JSON.stringify({traits:[],flags:[{id:1,feature:{id:1,name:'shikayat_onboarding'},feature_state_value:'guided',enabled:true,variant:'guided',metadata:{experiment:{id:1,name:'test',in_experiment:true}}}]}));
  }else if(req.url==='/v1/events'){
   events.push(...JSON.parse(body).events);res.end('{}');
  }else{res.statusCode=404;res.end('{}')}
 });
 server.listen(0,'127.0.0.1');await once(server,'listening');
 try{
  const port=server.address().port;
  const result=await run(['--ack-synthetic'],{FLAGSMITH_SYNTHETIC_ENVIRONMENT_ID:'test-public',FLAGSMITH_ENVIRONMENT_ID:'other-public',FLAGSMITH_SYNTHETIC_COUNT:'40',FLAGSMITH_API_URL:`http://127.0.0.1:${port}/api/v1/`,FLAGSMITH_EVENTS_URL:`http://127.0.0.1:${port}/`});
  assert.equal(result.code,0,result.err);assert.match(result.out,/SYNTHETIC: 40\/40/);
  assert.equal(events.filter(e=>e.event==='$flag_exposure').length,40);
  assert.ok(events.some(e=>e.event==='case_started'&&e.metadata?.traffic_type==='synthetic'));
 }finally{server.close();await once(server,'close')}
});
