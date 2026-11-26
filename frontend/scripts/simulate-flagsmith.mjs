/** Synthetic demo traffic. Use a separate Flagsmith environment and experiment. */
import {randomUUID,createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {Flagsmith} from '@flagsmith/nodejs';

if (!process.argv.includes('--ack-synthetic')) {
 console.error('Refusing to send: pass --ack-synthetic and use a dedicated test environment.');
 process.exit(2);
}
const environmentKey=process.env.FLAGSMITH_SYNTHETIC_ENVIRONMENT_ID;
let primaryKey=process.env.FLAGSMITH_ENVIRONMENT_ID;
if (!primaryKey) {
 try {
  const env=readFileSync(new URL('../../.env',import.meta.url),'utf8');
  primaryKey=env.match(/^\s*FLAGSMITH_ENVIRONMENT_ID\s*=\s*['\"]?([^'\"\s#]+)/m)?.[1];
 } catch { /* A missing .env is handled by the guard below. */ }
}
if (!environmentKey || !primaryKey || environmentKey===primaryKey) {
 console.error('Set FLAGSMITH_ENVIRONMENT_ID and a different FLAGSMITH_SYNTHETIC_ENVIRONMENT_ID for a dedicated test environment.');
 process.exit(2);
}
const count=Number(process.env.FLAGSMITH_SYNTHETIC_COUNT||40);
if (!Number.isInteger(count)||count<1||count>200) {
 console.error('FLAGSMITH_SYNTHETIC_COUNT must be an integer from 1 to 200.');process.exit(2);
}
const client=new Flagsmith({environmentKey,enableEvents:true,requestTimeoutSeconds:10,
 ...(process.env.FLAGSMITH_API_URL?{apiUrl:process.env.FLAGSMITH_API_URL}:{}),
 ...(process.env.FLAGSMITH_EVENTS_URL?{eventProcessorConfig:{eventsApiUrl:process.env.FLAGSMITH_EVENTS_URL}}:{})});
let enrolled=0,events=0;
try {
 for(let i=0;i<count;i++) {
  const identifier=`synthetic-${randomUUID()}`;
  const flag=await client.getExperimentFlag('shikayat_onboarding',identifier);
  if(!flag.experiment?.inExperiment||!['control','guided'].includes(String(flag.value))) continue;
  enrolled++;
  // Equal synthetic conversion probability in both arms: no fabricated winning treatment.
  const hash=createHash('sha256').update(identifier).digest().readUInt32BE(0);
  if(hash/0x100000000<0.4){client.trackEvent('case_started',{identifier,metadata:{traffic_type:'synthetic'}});events++}
 }
} finally {await client.close()}
console.log(`SYNTHETIC: ${enrolled}/${count} identities enrolled; ${events} case-start events queued. Check delivery and results in the test environment dashboard.`);
if(!enrolled){console.error('No enrolled identities. Check that the experiment is running and its flag values are configured.');process.exitCode=1}
