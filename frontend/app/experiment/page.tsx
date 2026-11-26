'use client';
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {ArrowLeft,ArrowRight,BarChart3,Eye,ShieldCheck} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Card} from '@/components/ui/card';

type Variant='control'|'guided';
type Snapshot={data_source:string;captured_at:string;description:string;dashboard_url:string;arms:{name:string;exposures:number;case_starts:number;rate_percent:number}[]};
export default function ExperimentPage(){
 const [variant,setVariant]=useState<Variant>('control');
 const [configured,setConfigured]=useState<boolean|null>(null);
 const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
 useEffect(()=>{fetch('/api/experiment/config').then(r=>r.json()).then((x:{environment_id:string})=>setConfigured(Boolean(x.environment_id))).catch(()=>setConfigured(false));fetch('/api/experiment/synthetic-results').then(r=>r.json()).then((x:Snapshot)=>{if(x.data_source==='synthetic')setSnapshot(x)}).catch(()=>{})},[]);
 return <main className="mx-auto max-w-5xl px-6 py-12 space-y-12">
  <Link href="/" className="inline-flex items-center gap-2 text-sm text-link"><ArrowLeft size={16}/> Back to Shikayat</Link>
  <section className="max-w-3xl space-y-5"><div className="eyebrow text-link">TOGGLE WARS · TRACK 01</div>
   <h1 className="text-4xl md:text-5xl tracking-tight font-medium">Will a clearer first step help someone start?</h1>
   <p className="text-base text-zinc-600 leading-7">A consumer complaint is already stressful. We are testing whether a short, three-step explanation helps people begin a case more often than the existing one-line introduction.</p>
   <div className="flex flex-wrap gap-3"><span className="rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-800">One experiment</span><span className="rounded-full bg-stone-100 px-3 py-1 text-xs text-stone-700">Opt-in participation</span><span className="rounded-full bg-stone-100 px-3 py-1 text-xs text-stone-700">No complaint data sent</span></div>
  </section>
  <div className="grid gap-5 md:grid-cols-3">
   <Card className="p-5 gap-2"><Eye size={19} className="text-link"/><p className="text-xs text-zinc-500">EXPOSURE</p><p className="text-sm font-medium">An opted-in visitor sees an assigned version.</p></Card>
   <Card className="p-5 gap-2"><BarChart3 size={19} className="text-link"/><p className="text-xs text-zinc-500">PRIMARY METRIC</p><p className="text-sm font-medium">Starts a case, including a sample case.</p></Card>
   <Card className="p-5 gap-2"><ShieldCheck size={19} className="text-link"/><p className="text-xs text-zinc-500">PRIVACY</p><p className="text-sm font-medium">No case details; the SDK sends event metadata.</p></Card>
  </div>
  <section className="space-y-5"><div><h2 className="text-2xl font-medium">The two experiences</h2><p className="mt-2 text-sm text-zinc-500">Preview only. This switch does not assign a variant or record events.</p></div>
   <div className="flex gap-2"><Button variant={variant==='control'?'default':'outline'} onClick={()=>setVariant('control')}>A · Current</Button><Button variant={variant==='guided'?'default':'outline'} onClick={()=>setVariant('guided')}>B · Guided</Button></div>
   <Card className="p-8 gap-4"><div className="eyebrow text-link">YOU DON’T HAVE TO CHASE ALONE</div><h3 className="text-2xl font-medium">Kya hua? Screenshot bhejo ya bolo.</h3><p className="text-sm leading-7 text-zinc-600">{variant==='control'?'Send evidence → Approve → Shikayat follows up until you’re resolved.':'1. Share a screenshot or a few words.  2. Review your complaint.  3. Track the company’s reply.'}</p><div className="rounded-lg border border-dashed p-5 text-sm text-zinc-500">Drop screenshots here, or browse</div></Card>
  </section>
  {snapshot&&<section className="space-y-4"><div className="eyebrow text-link">SYNTHETIC DATA · WIRING CHECK</div><h2 className="text-2xl font-medium">A real Flagsmith run, with simulated visitors.</h2><p className="text-sm leading-6 text-zinc-600">{snapshot.description} This confirms the pipeline records exposures and events; it does not tell us which experience helps people.</p><Card className="p-6 gap-5">{snapshot.arms.map((arm,i)=><div key={arm.name} className="space-y-2"><div className="flex justify-between gap-4 text-sm"><span>{arm.name} · {arm.exposures} exposures · {arm.case_starts} starts</span><span className="tabular-nums">{arm.rate_percent}%</span></div><div className="h-2 rounded-full bg-zinc-100"><div className={`h-2 rounded-full ${i?'bg-indigo-700':'bg-zinc-400'}`} style={{width:`${arm.rate_percent}%`}}/></div></div>)}<p className="text-xs text-zinc-500">Snapshot: {new Date(snapshot.captured_at).toLocaleString('en-GB',{timeZone:'UTC'})} UTC · No winner claimed. <a className="underline text-link" href={snapshot.dashboard_url} target="_blank" rel="noreferrer">Open Flagsmith dashboard</a> (sign-in required).</p></Card></section>}
  <section className="grid gap-5 md:grid-cols-2"><Card className="p-6 gap-3"><h2 className="text-lg font-medium">How we will measure it</h2><p className="text-sm leading-6 text-zinc-600">Flagsmith assigns opted-in visitors to A or B and records exposure only when the assigned experience is shown. A case start is counted once per participant. The hypothesis is directional, not a promised outcome.</p><p className="text-xs leading-5 text-zinc-500">We will report counts for each group, conversion rates, uncertainty and limitations. Synthetic traffic will be run only in a separate environment and labelled as synthetic.</p></Card>
   <Card className="p-6 gap-3"><h2 className="text-lg font-medium">Current status</h2><p className="text-sm leading-6 text-zinc-600">{configured===null?'Checking configuration…':configured?'A Flagsmith environment is configured. Check its dashboard for the experiment’s real status and results.':'No Flagsmith environment is connected yet. No experiment results are being claimed.'}</p><a href="https://docs.flagsmith.com/experimentation/run-an-experiment" target="_blank" rel="noreferrer" className="text-sm text-link underline">How Flagsmith records an experiment <ArrowRight size={14} className="inline"/></a></Card></section>
 </main>;
}
