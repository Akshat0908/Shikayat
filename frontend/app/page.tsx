"use client";
import { useEffect, useState } from "react";
import { ShieldCheck, ArrowRight, CircleCheck, Radio } from "lucide-react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { getHealth } from "@/lib/api";

export default function Home() {
  const [health, setHealth] = useState("Connecting…");
  const [live, setLive] = useState(false);
  async function check() {
    try { await getHealth(); setHealth("Backend connected"); }
    catch { setHealth("Backend unavailable"); toast.error("Connection failed. Use Check connection to retry."); }
  }
  useEffect(() => {
    let active = true;
    getHealth().then(() => { if (active) setHealth("Backend connected"); }).catch(() => { if (active) setHealth("Backend unavailable"); });
    const events = new EventSource("/api/events");
    events.onopen = () => setLive(true);
    events.onerror = () => setLive(false);
    return () => { active = false; events.close(); };
  }, []);
  return <div className="min-h-screen bg-zinc-50/70">
    <header className="border-b bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
      <div className="flex items-center gap-2.5 text-lg font-semibold"><ShieldCheck className="size-6 text-primary" />Shikayat</div>
      <span className="rounded-full border bg-zinc-50 px-3 py-1 text-xs text-zinc-600">Builder preview</span>
    </div></header>
    <main className="mx-auto max-w-3xl px-6 py-20 sm:py-28">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="rounded-2xl border bg-white p-8 shadow-sm sm:p-12">
        <div className="mb-7 flex size-12 items-center justify-center rounded-xl bg-indigo-50"><ShieldCheck className="size-6 text-primary" /></div>
        <p className="mb-3 text-xs font-medium uppercase tracking-widest text-primary">Your complaint. A clear path forward.</p>
        <h1 className="max-w-lg text-2xl font-semibold tracking-tight">AI that fights customer care for you.</h1>
        <p className="mt-4 max-w-lg text-sm leading-7 text-zinc-600">Kya hua? Screenshot bhejo ya bolo. We’re building a calmer way to file complaints, track replies, and follow through.</p>
        <div className="my-8 space-y-4 text-sm text-zinc-600">{["Send evidence", "Approve the complaint", "Shikayat follows up until you’re paid"].map((step, i) => <div key={step} className="flex items-center gap-3"><span className="flex size-6 items-center justify-center rounded-full bg-zinc-100 text-xs font-medium text-zinc-700">{i+1}</span>{step}</div>)}</div>
        <div className="rounded-lg border border-dashed p-4 text-sm text-zinc-600">The foundation is ready. Case intake is coming next.</div>
        <Button variant="outline" className="mt-5" onClick={check}>Check connection<ArrowRight className="size-4" /></Button>
        <p className="mt-7 text-xs leading-5 text-zinc-500">Emails go from your mailbox. Nothing is sent without your approval.</p>
      </motion.div>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-5 text-xs text-zinc-600"><span className="flex items-center gap-2"><CircleCheck className="size-3.5" />{health}</span><span className="flex items-center gap-2"><Radio className="size-3.5" />{live ? "Live updates connected" : "Connecting live updates…"}</span></div>
    </main>
  </div>;
}
