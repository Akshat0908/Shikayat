'use client';
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {ShieldCheck} from 'lucide-react';
import {Card} from '@/components/ui/card';
import {api} from '@/lib/api';

type Company={id:string;name:string;sector:string|null;contact_verified:boolean;sandbox:boolean};
export default function Companies(){
 const [companies,setCompanies]=useState<Company[]|null>(null),[failed,setFailed]=useState(false);
 useEffect(()=>{api.directory().then(setCompanies).catch(()=>setFailed(true))},[]);
 return <main className="mx-auto max-w-7xl px-6 py-10 space-y-8"><Link href="/" className="text-sm text-link">← Back to cases</Link><div><div className="eyebrow">COMPANY DIRECTORY</div><h1 className="mt-3 text-3xl">Find the right place to start.</h1><p className="mt-3 text-sm text-zinc-600">Contact details are reviewed before a complaint is sent.</p></div>{failed?<p>Could not load companies. Please refresh.</p>:!companies?<p>Loading companies…</p>:<div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{companies.map(company=><Card key={company.id} className="p-5 gap-3"><div className="flex items-center gap-3"><span className="company-initial">{company.name.charAt(0)}</span><h2 className="text-base font-medium">{company.name}</h2></div>{company.sandbox&&<p className="text-xs text-zinc-600">Sandbox merchant · auto-replies for testing</p>}<p className="text-xs text-zinc-600">{company.contact_verified?<><ShieldCheck className="inline mr-1" size={14}/>Contact available for review</>:'Contact needs verification'}</p></Card>)}</div>}</main>;
}
