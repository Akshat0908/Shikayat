'use client';
import {useState} from 'react';
import {toast} from 'sonner';
import {Button} from '@/components/ui/button';
import {api} from '@/lib/api';
import type {ContactDiscoveryResult} from '@/lib/types';

export function ContactDiscovery({companyId,role,onConfirmed}:{companyId:string;role:'grievance_officer'|'nodal_officer';onConfirmed:()=>Promise<void>}) {
 const [result,setResult]=useState<ContactDiscoveryResult|null>(null),[busy,setBusy]=useState(false);
 async function find(domain?:string){setBusy(true);try{setResult(await api.discoverContact(companyId,role,domain))}catch(e){toast.error(e instanceof Error?e.message:'Could not find contact')}finally{setBusy(false)}}
 async function confirm(){setBusy(true);try{await api.confirmContact(companyId,role);setResult(null);await onConfirmed();toast.success('Contact confirmed. Review the recipient before sending.')}catch(e){toast.error(e instanceof Error?e.message:'Could not confirm contact')}finally{setBusy(false)}}
 return <div className="space-y-3"><Button size="sm" variant="outline" disabled={busy} onClick={()=>void find()}>{busy?'Searching official sources…':'Find official contact'}</Button>{result?.status==='confirm_domain'&&<div className="space-y-2 text-sm"><p>Is <strong>{result.domain}</strong> the official company domain? Search will be restricted to this domain.</p><Button size="sm" variant="outline" disabled={busy} onClick={()=>void find(result.domain)}>Confirm official domain</Button></div>}{result?.status==='domain_unknown'&&<p className="text-sm text-amber-700">Official domain not found. Verify the contact manually.</p>}{result?.lead&&<div className="space-y-2 text-sm"><p className="text-amber-700 font-medium">{result.status==='awaiting_confirmation'?'Found on official site — awaiting your confirmation':'Unverified lead (not trusted)'}</p><p className="break-all">{result.lead.email??'Email unavailable'}</p>{result.lead.source_url?.startsWith('https://')&&<a className="text-primary underline break-all" href={result.lead.source_url} target="_blank" rel="noreferrer">View source</a>}<blockquote className="border-l-2 pl-3 text-zinc-600 whitespace-pre-wrap">{result.lead.evidence_quote??'No supporting quote available.'}</blockquote>{result.errors?.map(error=><p key={error} className="text-amber-700 text-xs">{error}</p>)}{result.status==='awaiting_confirmation'&&<Button size="sm" disabled={busy} onClick={()=>void confirm()}>Confirm contact</Button>}</div>}</div>;
}
