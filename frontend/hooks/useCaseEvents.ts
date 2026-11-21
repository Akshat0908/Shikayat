'use client';
import {useEffect,useRef,useState} from 'react';
import {ensureVisitor} from '@/lib/api';
export function useCaseEvents(onChange:()=>void,onProgress:(stage:string)=>void){
 const [connected,setConnected]=useState(false);const change=useRef(onChange),progress=useRef(onProgress);useEffect(()=>{change.current=onChange;progress.current=onProgress},[onChange,onProgress]);
 useEffect(()=>{let source:EventSource|undefined;let cancelled=false;void ensureVisitor().then(()=>{if(cancelled)return;source=new EventSource('/api/events');source.onopen=()=>{setConnected(true);change.current()};source.onerror=()=>setConnected(false);
 for(const name of ['decision','sent','draft','resolved','clock','case_changed'])source.addEventListener(name,()=>change.current());
 source.addEventListener('progress',(e:MessageEvent<string>)=>{try{const value=JSON.parse(e.data) as {stage?:string};if(value.stage)progress.current(value.stage);}catch{}});
 }).catch(()=>setConnected(false));return ()=>{cancelled=true;source?.close()}},[]);
 useEffect(()=>{const timer=setInterval(()=>change.current(),connected?10000:2000);return()=>clearInterval(timer)},[connected]);return connected;
}
