'use client';
import {useEffect,useRef,useState} from 'react';
export function useCaseEvents(onChange:()=>void,onProgress:(stage:string)=>void){
 const [connected,setConnected]=useState(false);const change=useRef(onChange),progress=useRef(onProgress);useEffect(()=>{change.current=onChange;progress.current=onProgress},[onChange,onProgress]);
 useEffect(()=>{const source=new EventSource('/api/events');source.onopen=()=>{setConnected(true);change.current()};source.onerror=()=>setConnected(false);
 for(const name of ['decision','sent','draft','resolved','clock','case_changed'])source.addEventListener(name,()=>change.current());
 source.addEventListener('progress',(e:MessageEvent<string>)=>{try{const value=JSON.parse(e.data) as {stage?:string};if(value.stage)progress.current(value.stage);}catch{}});
 return ()=>source.close()},[]);
 useEffect(()=>{const timer=setInterval(()=>change.current(),connected?10000:2000);return()=>clearInterval(timer)},[connected]);return connected;
}
