'use client';
import {useEffect} from 'react';
import {useRouter} from 'next/navigation';
import {api} from '@/lib/api';

export function AdminShortcut(){
 const router=useRouter();
 useEffect(()=>{
  const handler=(event:KeyboardEvent)=>{
   const target=event.target;
   if(!event.shiftKey||event.ctrlKey||event.metaKey||event.altKey||event.key.toLowerCase()!=='d'||target instanceof HTMLInputElement||target instanceof HTMLTextAreaElement||(target instanceof HTMLElement&&target.isContentEditable))return;
   void api.adminStatus().then(status=>{if(status.admin)router.push('/admin/')}).catch(()=>{});
  };
  window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);
 },[router]);
 return null;
}
