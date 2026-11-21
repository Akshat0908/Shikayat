# Codex prompt pack: Shikayat

Put `AGENTS.md` in the repo root first. Codex reads it automatically.
Paste these **in order**. Each prompt is one Codex task. Don't start the next one until the current one is green and committed.
Run two Codex threads in parallel: **Thread A = backend** (prompts A1–A6) and **Thread B = frontend** (prompts B1–B3). Merge at prompt M1.

---

## A0: Scaffold (Thread A, ~12:50–1:15)

```
Read AGENTS.md fully. Then scaffold the repo exactly as described in section 5 ("Directory layout"):
- backend/ FastAPI app with config (pydantic-settings reading .env), SQLModel + SQLite db, all models from section 6, a /api/health route, and an SSE endpoint /api/events (an in-process pub/sub; publish a "ping" every 15s).
- frontend/ Next.js (App Router, TypeScript, Tailwind, ESLint) with shadcn/ui initialised (neutral base), lucide-react, framer-motion, sonner. next.config: output 'export'; in dev, rewrite /api/* to http://localhost:8000.
- FastAPI serves frontend/out at / in production.
- data/companies.json and data/legal_refs.json seeded exactly per section 6 (ShopKart demo company + 25 real companies with email null and verified false; never invent emails).
- .env.example per section 5, .gitignore, Makefile (dev, test, build, eval, docker), a multi-stage Dockerfile, and a Caddyfile for <ip>.sslip.io.
- `make dev` must run backend :8000 + frontend :3000 together.
Acceptance: `make dev` works, /api/health returns ok, the frontend loads a placeholder page, `make test` passes (add 1 smoke test). Commit.
```

## A1: LLM client + case understanding (Thread A, ~1:15–2:30)

```
Implement section 7 steps 1–4.
- ai/client.py: call_structured(task, model, schema, instructions, text, images=[]) using the OpenAI Responses API with Structured Outputs (Pydantic). Check the current official docs for the exact SDK call and parameters; do not guess. Add a 30s timeout, 2 retries, a disk cache keyed by sha256 of (model, instructions, inputs), a LlmCall log row with a token-based cost estimate, and a budget guard (BUDGET_USD).
- ai/transcribe.py using TRANSCRIBE_MODEL with Hindi+English hints and a Roman-script Hinglish instruction (check the docs for the exact params).
- ai/extract_case.py producing CaseFacts per section 7 step 2. Never guess: null + missing_info.
- engine/company.py (rapidfuzz on name + aliases, MODEL_FAST only for ties) and engine/strength.py (deterministic 0–100 + labels; MODEL_FAST 1-line rationale).
- POST /api/cases (multipart: images[], audio?, text?) → creates Case + Evidence, runs the pipeline, publishes SSE progress events for each stage ("reading_screenshots", "transcribing", "finding_officer", "assessing", "done"), and returns the case.
- data/samples/: create 3 sample cases (section 8) as realistic screenshots rendered from HTML with Playwright or PIL (fictional brands only, no real logos) + text. POST /api/cases/sample/{id}.
- Unit tests for strength.py and company matching.
Acceptance: the ShopKart sample returns correct facts and "Strong". Commit.
```

## A2: Draft, approve, send (Thread A, ~2:30–3:30)

```
Implement section 7 step 5 and sending.
- engine/deadlines.py: compute ack_48h and resolve_30d from sent_at using demo-clock-aware now().
- ai/draft_complaint.py → EmailDraft. Pass only verified legal refs from legal_refs.json and the code-computed deadline date. Under 220 words. Tests ensure there are no citations outside the allowed list.
- POST /api/cases/{id}/draft, POST /api/cases/{id}/approve (sends).
- mail/smtp_send.py: Gmail SMTP with an app password; set Message-ID; store it; In-Reply-To/References for follow-ups. Respect SEND_ENABLED and the safety rules in section 7 (never send to null/unverified; approval is required for non-allowlisted recipients).
- Every step writes an Event with actor + reason, published over SSE.
Acceptance: approving the ShopKart case delivers a real email to DEMO_COMPANY_EMAIL; deadlines are created. Commit.
```

## A3: Inbox watcher, classifier, policy engine (Thread A, ~3:30–5:30)

```
Implement section 7 steps 6–8.
- mail/imap_poll.py (imap-tools): every 5s, fetch new mail in USER_EMAIL's inbox, match it to a case by In-Reply-To/References (fallback: subject + sender), and store it as an inbound Message.
- ai/classify_reply.py → ReplyAnalysis + the deterministic deflection check.
- engine/policy.py: a pure-function state machine exactly per section 7 step 7. Every Decision has a human-readable reason. Thorough pytest coverage of every transition, including the 48h breach via the demo clock.
- ai/draft_escalation.py; L4 produces NCH-ready text + link (no submission).
- A background worker ties it together: inbound → classify → decide → (autopilot if allowlisted, else create a pending approval) → send → events.
- A deadline ticker every 10s marks deadlines met/breached and triggers policy.
Acceptance: policy tests pass; a manual reply to the thread from the demo inbox gets classified and produces the right next action. Commit.
```

## A4: Demo mode (Thread A, ~5:30–6:30)

```
Implement section 8 completely: demo/company_bot.py (3 scripted replies in-thread with DEMO_REPLY_DELAY_SECONDS), the demo clock (+48h endpoint, offset used everywhere), POST /api/demo/inject (next scripted reply inserted locally as if received), POST /api/demo/reset, and replay via the LLM cache.
Run the full hero flow from section 12, steps 1–5, via a script `scripts/demo_e2e.py` that drives the API and asserts each state.
Acceptance: demo_e2e.py passes twice in a row; the second run is fast (cache). Commit.
```

## B1: UI shell with mock data (Thread B, start ~1:15, in parallel)

```
Read AGENTS.md, especially section 9 (UI design system). This is the most visible part of the product: make it look like a funded startup's product, not a template.
Build the full UI against a typed mock API (lib/mock.ts) with the same types the backend will return (lib/types.ts):
- The three-column layout from section 9: Cases list | Messenger chat | Case Board (facts card with confidence dots + missing-info chips, strength meter, escalation ladder stepper L2→L5, live deadline countdowns, timeline with actor icons and an expandable "why").
- Empty state with 3 sample chips, drag-and-drop, and a mic recorder (MediaRecorder, waveform while recording).
- An AI "thinking" step indicator (never a bare spinner).
- Email preview dialog styled like a real email client, with highlighted citations + deadline, and Edit / Approve & send.
- First-run onboarding (3 steps + privacy note), sonner toasts, skeletons.
- Brand: Geist font, indigo #4338CA accent, ShieldCheck wordmark, custom favicon, page titles.
- Responsive: under 1024px the Case Board becomes a tab.
- Subtle framer-motion on timeline items and status changes.
Use shadcn components (Card, Badge, Button, Dialog, Tabs, Tooltip, Progress, ScrollArea, Separator, Skeleton). Mock the full hero story (section 12) with a "simulate" dev button so I can screenshot every state.
Acceptance: `npm run build` passes with zero warnings; every state is screenshot-ready. Commit.
```

## B2: Proof page + polish (Thread B, ~4:00–5:30)

```
Build /proof: headline numbers (baseline vs Shikayat) as stat tiles, a clean horizontal bar chart per metric (use simple SVG or recharts with the design system colours), a table of the 20 cases with pass/fail per metric, and an expandable side-by-side view of baseline email vs Shikayat email for any case. Read from /api/eval/latest (mock it for now).
Then do a polish pass over all screens against the section 9 checklist: spacing rhythm (4/8px), alignment, typography scale, empty/loading/error states, focus states, contrast, no console errors.
Commit.
```

## M1: Integrate (Thread A, ~6:30–8:00) — **checkpoint: by 8 PM the hero flow works in the browser**

```
Replace the frontend mock with the real API: typed client in lib/api.ts, SSE subscription in a useCaseEvents hook (auto-reconnect), optimistic UI for approve. Wire the "thinking" step indicator to the SSE progress events. Add the hidden demo controls (⏩ +48h, inject Ctrl+Shift+R, reset) visible only when DEMO_MODE is true, in a small unobtrusive "Demo" pill in the corner.
Run section 12 steps 1–5 in the browser end to end. Fix everything that breaks.
Acceptance: the full hero flow works in the browser with real email, twice in a row. Commit.
```

## A5: Evaluation (Thread A, ~8:00–10:00)

```
Implement section 10: create eval/cases/ (20 cases, synthetic, paraphrased, no personal data, with ground truth), eval/run_eval.py (baseline vs Shikayat, deterministic checks, cost/latency), results JSON + console markdown table, and GET /api/eval/latest for /proof.
Run it. If any Shikayat metric is weak, show me the failing cases and propose the smallest fix; don't overfit to the eval.
Commit.
```

## A6: Deploy (Thread A, ~10:00–12:00) — **checkpoint: by midnight there's a live HTTPS URL**

```
Prepare deployment to a fresh EC2 Ubuntu instance: scripts/deploy.sh that installs Docker, builds the image, runs it with --restart always and the .env file, and runs Caddy for https://<ip-with-dashes>.sslip.io reverse-proxying to the app. Document the exact steps in DEPLOY.md (security group ports 80/443/22, Elastic IP). Make sure the mic works over HTTPS and SSE works through Caddy (disable buffering).
Acceptance: I can run the hero flow on the public URL from my phone. Commit.
```

## A7: README + final polish (~12:00–2:00 AM, then again Sunday morning)

```
Write README.md exactly per AGENTS.md section 13 (leave placeholders for the GIF, video link and proof numbers, then fill the numbers from eval/results). Add a Mermaid pipeline diagram. Then do a final review pass: remove dead code, make sure `make test` and `make build` pass, there are no console errors and no TODOs in user-visible strings, and .env.example is complete. List anything risky for a live demo.
```

---

## Emergency prompts

**Something is broken and you're short on time:**
```
Stop adding features. Reproduce the bug with a failing test or script first, then make the smallest fix. Show me the diff and how you verified it.
```

**The UI looks generic:**
```
Audit the current UI against AGENTS.md section 9 like a strict senior product designer. List the top 10 issues that make it look like a template (spacing, hierarchy, typography, colour, density, empty states), then fix them one by one. Show before/after reasoning for each.
```

**Freeze mode (Sunday 9:30 AM onwards):**
```
We are in feature freeze. Only fix bugs that would break the demo or the build. No refactors, no new dependencies.
```
