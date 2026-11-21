'use client';
import {motion} from 'framer-motion';
import {Check} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Card} from '@/components/ui/card';
import type {Board, CaseRecord} from '@/lib/types';

const money=(n:number|null|undefined)=>n==null?'Unknown':new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(n);
function highlight(body:string,quotes:string[]){
 const spans=quotes.flatMap(q=>{if(!q)return [];const matches:{start:number;end:number}[]=[];let i=body.indexOf(q);while(i>=0){matches.push({start:i,end:i+q.length});i=body.indexOf(q,i+q.length)}return matches}).sort((a,b)=>a.start-b.start);
 let cursor=0;const parts:React.ReactNode[]=[];
 for(const span of spans){if(span.start<cursor)continue;parts.push(body.slice(cursor,span.start),<mark key={span.start} className="bg-amber-100 text-zinc-900 rounded-sm">{body.slice(span.start,span.end)}</mark>);cursor=span.end}
 parts.push(body.slice(cursor));return parts;
}
export function Journey({board,c}:{board:Board|null,c:CaseRecord}){
 const events=board?.events??[], messages=board?.messages??[];
 const done=[events.some(e=>e.type==='sent'),messages.some(m=>m.direction==='in'),messages.some(m=>m.direction==='in'&&!!m.classification_json.reply_type),events.some(e=>e.type==='decision'),c.status==='RESOLVED'];
 const current=c.status==='RESOLVED'?4:!done[0]?0:!done[1]?1:!done[2]?2:3;
 const state=[c.status==='DRAFT'||c.status==='AWAITING_APPROVAL'?'Draft ready · waiting for your approval':'Complaint sent','Waiting for a company reply','Reading the reply','Reviewing the next action','Receipt confirmed'];
 return <Card className="p-5 gap-3"><div className="eyebrow">CASE JOURNEY</div><div className="space-y-3">{['Complaint approved','Company replied','Forensics verdict','Next action','Resolved'].map((label,i)=><motion.div key={label} initial={false} animate={{opacity:done[i]||i===current?1:.5,x:i===current?2:0}} transition={{duration:.2}} className={`flex items-start gap-2 text-xs ${i===4&&done[i]?'text-emerald-700 font-medium':i===current?'text-primary font-medium':''}`}><span className={`flex size-5 shrink-0 items-center justify-center rounded-full border ${done[i]?'bg-emerald-50 border-emerald-200 text-emerald-700':i===current?'bg-indigo-50 border-indigo-300':'border-zinc-300'}`}>{done[i]?<Check size={12}/>:i+1}</span><span>{label}{i===current&&<small className="block text-zinc-500 font-normal mt-1">{state[i]}</small>}</span></motion.div>)}</div></Card>
}
export function Forensics({board,c,counterAmount,setCounterAmount,onOffer}:{board:Board|null,c:CaseRecord,counterAmount:string,setCounterAmount:(v:string)=>void,onOffer:(action:'accept'|'counter')=>void}){
 const replies=board?.messages.filter(m=>m.direction==='in')??[];
 return <>{replies.map((m,i)=>{const f=m.classification_json;return <motion.div key={m.id} initial={{opacity:0,y:6}} animate={{opacity:1,y:0}} transition={{duration:.2}}><Card className="p-5 gap-3"><div className="text-xs">{m.classification_json.sender_verified?`Verified sender ✓ (${m.classification_json.verification_detail??'company domain'})`:'⚠️ Unverified sender'}</div>{m.classification_json.match_method==='order ID'&&<div className="text-xs text-zinc-500">Matched by order ID</div>}<div className="eyebrow">{m.subject==='User-reported update'?'USER-REPORTED FORENSICS':'REPLY FORENSICS'}</div><p className="text-xs whitespace-pre-wrap leading-5 text-zinc-700">{highlight(m.body_text,f.evidence_quotes??[])}</p><div className="border-t pt-3 text-xs leading-5 text-zinc-600">Acknowledged {f.acknowledged?'✓':'✗'} · Refund confirmed {f.refund_confirmed?'✓':'✗'} · Status: {(f.resolution_status??'unresolved').replaceAll('_',' ').replace(/^./,x=>x.toUpperCase())}</div>{f.acknowledged&&!f.refund_confirmed&&<strong className="text-sm">Acknowledged ≠ Resolved</strong>}{f.reply_type==='partial_offer'&&<p className="text-sm font-medium">Offered {money(f.offered_amount_inr)}{/(voucher|coupon|store credit|gift card)/i.test(m.body_text)?' voucher':''} vs {f.original_remedy??money(c.amount_inr)} requested</p>}<p className="text-xs leading-5"><span className="font-semibold">Next action:</span> {f.next_action??'Review reply'}</p><p className="text-xs text-zinc-500 leading-5">{f.reason}</p>{i===replies.length-1&&f.reply_type==='partial_offer'&&c.status==='NEEDS_INFO'&&<div className="flex flex-wrap gap-2"><Button size="sm" onClick={()=>onOffer('accept')}>Accept</Button><input aria-label="Counter amount" type="number" min="1" value={counterAmount} onChange={e=>setCounterAmount(e.target.value)} className="border rounded p-2 w-28 text-sm"/><Button size="sm" variant="outline" disabled={!Number(counterAmount)} onClick={()=>onOffer('counter')}>Counter</Button></div>}</Card></motion.div>})}</>
}
