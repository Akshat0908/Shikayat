'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import {createFlagsmithInstance} from '@flagsmith/flagsmith';

const FLAG='shikayat_onboarding';
const METRIC='case_started';
type Variant='control'|'guided';
type ExperimentConfig={environment_id:string;api_url:string|null;events_url:string|null};

/** The client is initialised only after explicit, per-session consent. */
export function useOnboardingExperiment(visible:boolean){
 const client=useRef<ReturnType<typeof createFlagsmithInstance>|null>(null);
 const visibleRef=useRef(visible),exposed=useRef(false),started=useRef(false);
 const [variant,setVariant]=useState<Variant>('control');
 const [status,setStatus]=useState<'idle'|'loading'|'active'|'unavailable'>('idle');
 const [assignment,setAssignment]=useState<{value:Variant;label:string}|null>(null);
 useEffect(()=>{visibleRef.current=visible},[visible]);

 const join=useCallback(async()=>{
  if(status==='loading'||status==='active')return;
  setStatus('loading');
  try{
   const response=await fetch('/api/experiment/config',{cache:'no-store'});
   if(!response.ok)throw new Error('Experiment unavailable');
   const config=await response.json() as ExperimentConfig;
   if(!config.environment_id)throw new Error('Experiment not configured');
   const instance=createFlagsmithInstance();
   // This random ID is for experimentation only and is not a case or account ID.
   const identity=sessionStorage.getItem('shikayat-experiment-id')||crypto.randomUUID();
   sessionStorage.setItem('shikayat-experiment-id',identity);
   await instance.init({environmentID:config.environment_id,identity,enableEvents:true,
    ...(config.api_url?{api:config.api_url}:{}),
    ...(config.events_url?{eventProcessorConfig:{eventsApiUrl:config.events_url}}:{})});
   const flag=instance.getAllFlags()[FLAG];
   if(!visibleRef.current||!flag?.enabled||!flag.experiment?.inExperiment||!flag.variant||!['control','guided'].includes(String(flag.value)))throw new Error('Not enrolled');
   client.current=instance;
   setAssignment({value:flag.value as Variant,label:flag.variant});
   setVariant(flag.value as Variant);setStatus('active');
  }catch{setStatus('unavailable')}
 },[status]);

 // A flag read does not count as exposure; record it after the assigned UI renders.
 useEffect(()=>{
  if(visible&&assignment&&!exposed.current&&client.current){
   client.current.trackExposureEvent(FLAG,{value:assignment.label});
   exposed.current=true;
  }
 },[visible,assignment]);

 const trackStart=useCallback(()=>{
  if(exposed.current&&!started.current&&client.current){
   client.current.trackEvent(METRIC);started.current=true;
   void client.current.flushEvents().catch(()=>{});
  }
 },[]);
 useEffect(()=>{const flush=()=>{if(client.current)void client.current.flushEvents().catch(()=>{})};
  window.addEventListener('pagehide',flush);return()=>window.removeEventListener('pagehide',flush)},[]);
 return {variant,status,join,trackStart};
}
