# AGENTS.md: Shikayat (Builders 2026)

> Codex reads this file automatically. It is the single source of truth for this project.
> Re-read it before every task. If a task conflicts with this file, ask before deviating.

---

## 0. Who you are working with and how to behave

- I am **Akshat Agrawal**, a solo builder (final-year M.Tech CSE, VIT Bhopal). I'm strong in Python, TS, React/Next.js, FastAPI, OpenAI APIs and conversational agents.
- You are my **senior co-engineer**. Be practical and opinionated. Ship working software.
- **HARD DEADLINE: code freeze Sunday 22 Nov 2026, 2:00 PM IST.** There are no late entries.
- Priority order: **(1) demo works end to end, every time → (2) UI looks like a real, premium product → (3) AI depth is visible → (4) everything else.**
- Never leave the app broken. Run tests and the build before saying "done". Commit after every green step.
- Prefer boring, reliable tech. Avoid new dependencies unless they clearly save time.
- When you are unsure about an OpenAI API parameter or model name, **check the official docs** (developers.openai.com). Don't guess, and isolate the call in one function.
- **Never invent** company email addresses, officer names, legal rule numbers, statistics or URLs. Unknown = `null` + shown as "needs verification" in the UI.
- After every task, reply with: what changed, how to run it, how to verify it, and what's next (max 10 lines).

---

## 1. The event (context so you make the right trade-offs)

- **Builders 2026**: Pan-India AI Builders Hackathon by **OpenAI × Equal AI, powered by AWS**, at Equal AI HQ, Hyderabad. Invite-only, **~100 builders**, picked from ~10,000.
- **Solo only.** All code is written during the event (open-source libraries are fine). Coding agents are allowed.
- Timeline: themes revealed Sat 21 Nov 10 AM → **code freeze Sun 2 PM** → judging 2–5:30 PM → grand finale 6 PM.
- **Submission:** code repo + working demo (deployed link or recording) + 4–5 slides (problem, what I built, how it works, what's next).
- **Selection:** 100 → **10 shortlisted** by the Equal AI team (judging code, demo and slides) → **3 winners** chosen by the jury after live demos. Prizes: ₹20L / ₹10L / ₹5L.
- **Judges score:** (1) a working end-to-end product demo, (2) AI-native, (3) presentation and craft.
- **Jury:** Karan MV (Developer Relations Leader, OpenAI India); Equal AI leaders Keshav Reddy (Founder & CEO), Akhilesh Damaraju (Co-founder) and Anil Kusuma. **Chief guests:** Shri Ajay Sawhney (former Secretary, MeitY) and Shri Abhishek Singh (former CEO, IndiaAI Mission).
- **Equal AI** builds "India's AI Messenger app": Personal AI Calls (today) → Personal AI Messaging (next) → Personal AI Experts (then). Their thesis: **Context → Intent → Actions → Fulfillment → deeper context. "Every lap deepens the profile."**
- **Our track: Build Creative.** "Personal context into everyday AI products. Show a working journey from raw input to a useful outcome. Stands out: an original idea backed by a working product."

**Implications for you:**
- The screening team sees ~100 repos in a few hours, so each gets 1–3 minutes. The **README and the first screen must hook within 10 seconds.**
- Judges notice the **UI first.** It must look like a funded startup's product, not a hackathon template.
- Live demo on **venue wifi.** Everything needs a fallback (cache, replay, demo mode).

---

## 2. Resources and budget

| Resource | Use |
|---|---|
| OpenAI API credits (~$250 total) | **Hard budget for this project: $120.** Use the cheap fast model by default and the smart model only where quality matters. Log every call's tokens, cost estimate and latency. |
| ChatGPT Pro + Codex | Coding agent (you). |
| AWS account | One EC2 instance (ap-south-2 Hyderabad or ap-south-1 Mumbai), Docker, Caddy for HTTPS. S3 for the backup demo video. |
| Gmail (2 accounts, app passwords) | Account A = the user's mailbox (sends complaints). Account B = the fictional demo company's grievance inbox. |

**Do NOT use:** telephony/Twilio, the WhatsApp Business API, scraping of logged-in sites, paid APIs that need approval, Lambda/API Gateway for uploads, a vector DB, or auth/multi-user systems.

---

## 3. The product

### Name
**Shikayat** (शिकायत), *"Your AI that fights customer care for you."*

### One-line pitch
Forward a screenshot, rant in a voice note, and walk away. Shikayat files the complaint with the right officer, enforces the company's legal deadlines, reads their replies, catches stalling, and escalates until you get your money back.

### Problem (only these verified facts may go in the UI/README)
- ServiceNow's India Customer Experience Intelligence Report (2024): the average Indian spends **30.7 hours a year on hold** with customer service.
- Under the **Consumer Protection (E-Commerce) Rules, 2020**, e-commerce entities must appoint a **grievance officer**, display their contact details, **acknowledge a complaint within 48 hours** and **redress it within one month.** People rarely use this because it's tedious, and companies count on people giving up.

### Persona
**Sunita, 34, Hyderabad.** She ordered from "ShopKart" (fictional), returned the item, and her ₹4,299 refund hasn't come in 3 weeks. She's called 4 times, got 2 ticket numbers, and nothing has happened.

### Core journey (raw input → useful outcome)
1. **Input:** 1–3 screenshots (order page, refund SMS, chat with support) + a Hinglish voice note or text.
2. **Understand:** transcribe, then extract the case facts (company, order ID, amount, dates, attempts, tickets, demand) with confidence scores, and list what's missing.
3. **Route:** resolve the company → its **escalation ladder** (L2 Grievance Officer → L3 Nodal Officer → L4 National Consumer Helpline → L5 Consumer Commission).
4. **Assess:** case strength score (deterministic) + a short rationale.
5. **Draft:** a firm, specific, polite complaint citing **only** the legal references in `legal_refs.json`, with a code-computed deadline date.
6. **Approve:** the user sees a real-looking email preview → "Approve & send".
7. **Send:** SMTP from the user's mailbox, with threading headers stored.
8. **Watch:** an IMAP poller reads replies on the thread.
9. **Classify:** acknowledgment / deflection (template stalling) / info request / resolution offer / partial / rejection. Extract the ticket ID, promised date and offered amount.
10. **Decide:** a **deterministic policy engine** (not the LLM) picks the next action: wait, reply with info, firm follow-up, escalate, or mark resolved. It always records a human-readable **reason**.
11. **Escalate:** draft and send to the next level. L4/L5 produce **ready-to-file text + an official link** (no automated portal submission).
12. **Close:** the user confirms the money was received → RESOLVED. The case is added to the user's profile (companies, disputes, outcomes).

---

## 4. Scope

### MUST (demo MVP)
- [ ] New case from screenshots + voice note/text (also 3 one-click **sample cases**)
- [ ] Case extraction with per-field confidence and a "missing info" list
- [ ] Company resolution from `data/companies.json` + escalation ladder
- [ ] Case strength score
- [ ] Complaint draft + email preview dialog + Approve & send (SMTP)
- [ ] IMAP inbox poller with thread matching
- [ ] Reply classifier + deterministic policy engine + escalation drafts
- [ ] Case Board: facts card, ladder stepper, live deadline countdowns, timeline with "why" for each AI decision
- [ ] Messenger-style chat panel (Hinglish micro-copy)
- [ ] **Demo mode:** demo company bot (auto-replies), ⏩ demo clock, replay cache, hidden "inject reply" (shortcut `Ctrl+Shift+R`)
- [ ] Live UI updates via SSE
- [ ] `/proof` page: eval results (baseline vs Shikayat)
- [ ] Deployed over HTTPS on EC2 + a polished README

### SHOULD (if time)
- [ ] Hindi summary of each email for the user
- [ ] Cases list with filters and a "₹ recovered" counter
- [ ] Cost/latency debug drawer (tokens and ₹ per case)
- [ ] Mobile-responsive layout (tabs)
- [ ] `/about` mini landing page

### CUT (explicitly not building)
- Phone calls, WhatsApp integration, auto-submission to government portals, auth, multi-user, payments, fine-tuning, a vector DB.

---

## 5. Architecture and stack

```
Browser (Next.js static export, served by FastAPI)
   │  REST + SSE (/api/events)
FastAPI (Python 3.11)
   ├─ api/          routes: cases, evidence upload, approve, inject, demo clock, eval results
   ├─ ai/           one file per LLM task, Pydantic schemas, cached + logged
   ├─ engine/       policy.py (state machine), deadlines.py, strength.py (all deterministic)
   ├─ mail/         smtp_send.py, imap_poll.py (imap-tools), threading helpers
   ├─ demo/         company_bot.py (auto-replier for the demo inbox), clock.py
   ├─ workers       asyncio background tasks: inbox poller (5s), deadline ticker (10s), demo bot (5s)
   └─ db            SQLite via SQLModel
```

**Backend:** FastAPI, SQLModel/SQLite, `openai`, `pydantic`, `imap-tools`, `aiosmtplib` (or smtplib in a thread), `python-multipart`, `rapidfuzz`, `python-dotenv`, `pytest`.

**Frontend:** Next.js (App Router, TS) + Tailwind + **shadcn/ui** + `lucide-react` + `framer-motion` (subtle) + `sonner` (toasts). `output: 'export'`, served by FastAPI from `/`. In dev, Next runs on :3000 and proxies `/api` to :8000.

**Deploy:** a single Dockerfile (multi-stage: build Next → copy `out/` into the Python image). EC2 t3.small + Docker + **Caddy** with an `<ip>.sslip.io` hostname for automatic HTTPS (the mic requires HTTPS).

### OpenAI models (all from env vars, never hard-coded)
| Env var | Job | Default (verify on developers.openai.com before use) |
|---|---|---|
| `TRANSCRIBE_MODEL` | Voice note → text (language hints hi + en, Roman script) | `gpt-transcribe` |
| `MODEL_SMART` | Screenshot + transcript → case facts; complaint and escalation drafting | current mid-tier GPT model with vision + Structured Outputs (e.g. a GPT-6.x "Sol/Terra" tier) |
| `MODEL_FAST` | Reply classification, company matching tie-breaks, short rationales, chat micro-replies | current small/fast tier (e.g. "Luna") |

- Use the **Responses API** with **Structured Outputs** (Pydantic models) for every extraction/classification call. Images are passed as input images (base64 data URLs).
- Every LLM call goes through `ai/client.py::call_structured(...)`. It handles a 30s timeout, 2 retries with backoff, a disk cache keyed by `sha256(model + prompt + inputs)`, and a log row in `llm_calls` (model, tokens, est. cost, latency).
- The budget guard refuses calls once the logged spend exceeds `BUDGET_USD` (default 100).

### Directory layout
```
shikayat/
├─ AGENTS.md  README.md  .env.example  Dockerfile  Caddyfile  Makefile
├─ backend/app/{main.py, config.py, db.py, models.py, events.py}
├─ backend/app/{api,ai,engine,mail,demo}/...
├─ backend/tests/
├─ data/{companies.json, legal_refs.json, samples/}
├─ eval/{cases/, run_eval.py, results/}
└─ frontend/ (Next.js)
```

### Env (`.env.example`)
```
OPENAI_API_KEY=
TRANSCRIBE_MODEL=gpt-transcribe
MODEL_SMART=
MODEL_FAST=
BUDGET_USD=100
USER_EMAIL=            # Gmail A (sender)
USER_EMAIL_APP_PASSWORD=
DEMO_COMPANY_EMAIL=    # Gmail B (fictional ShopKart grievance inbox)
DEMO_COMPANY_APP_PASSWORD=
DEMO_MODE=true
DEMO_REPLY_DELAY_SECONDS=20
SEND_ENABLED=true      # global kill switch
AUTOPILOT_ALLOWLIST=   # comma-separated emails where escalations may auto-send (demo only)
```

---

## 6. Data model

- **Case**: id, title, company_id, status (state machine), level (L2…L5), facts_json, strength_score, strength_label, demand, amount_inr, created_at, resolved_at, recovered_inr
- **Evidence**: id, case_id, kind (screenshot | voice | text), path, transcript, extracted_json
- **Message**: id, case_id, direction (out | in), level, to, from, subject, body_text, message_id, in_reply_to, sent_at, classification_json
- **Event** (timeline): id, case_id, at, actor (ai | user | company | system), type, title, reason, payload_json
- **Deadline**: id, case_id, kind (ack_48h | resolve_30d | followup), due_at, status (running | met | breached)
- **LlmCall**: id, task, model, input_tokens, output_tokens, est_cost_usd, latency_ms, cached, at
- **Settings**: demo_clock_offset_seconds, autopilot (bool)

### `data/companies.json` (seed)
Fields: `id, name, aliases[], sector, care_url, grievance_officer{name, email, source_url, verified}, nodal_officer{name, email, source_url, verified}, regulator_route`.
- Include **"ShopKart"** (fictional demo company): the grievance email comes from env `DEMO_COMPANY_EMAIL`, `verified: true`, `demo: true`.
- Include ~25 real companies (Flipkart, Amazon India, Myntra, Meesho, Ajio, Nykaa, Swiggy, Zomato, Zepto, Blinkit, BigBasket, Tata CLiQ, Croma, Reliance Digital, JioMart, Ola, Uber, Rapido, MakeMyTrip, Goibibo, IndiGo, Air India, Airtel, Jio, Vi) with **email = null, verified = false** and `care_url` only if you are sure of it. Akshat will fill and verify them by hand from the companies' official grievance pages. **Do not invent emails.**

### `data/legal_refs.json`
Only references with a source URL and `verified: true` may be cited in drafts. Seed:
- `ecom_rules_2020_grievance`: "Consumer Protection (E-Commerce) Rules, 2020: grievance officer must acknowledge within 48 hours and redress within one month". The exact rule number is left blank until Akshat verifies it.
- `cpa_2019`: "Consumer Protection Act, 2019".
- `nch`: National Consumer Helpline (toll-free 1915, portal URL to be verified).
- `consumer_commission`: e-filing route (portal name and URL to be verified).

---

## 7. AI pipeline (each step is small, typed and testable)

1. **`ai/transcribe.py`**: voice → text (`TRANSCRIBE_MODEL`, language hints hi/en, instruct Roman-script Hinglish).
2. **`ai/extract_case.py`** (`MODEL_SMART`, images + transcript + text) → `CaseFacts`:
   `company_name, order_id, amount_inr, purchase_date, issue_type (refund_not_received | wrong_item | not_delivered | damaged | overcharged | cancellation | service_failure | other), issue_summary_en, user_demand (refund | replacement | delivery | compensation | other), events[{date, what}], contact_attempts[{date, channel, ticket_id}], days_elapsed, missing_info[], field_confidence{field: 0–1}`.
   **Rule:** never guess. Unknown → null + add it to `missing_info`.
3. **`engine/company.py`**: fuzzy-match to `companies.json` (rapidfuzz); `MODEL_FAST` only breaks ties. Return the ladder.
4. **`engine/strength.py`** (deterministic, 0–100): evidence present, amount known, order ID, dates, attempts made, days elapsed past the promised timeline, ticket IDs. Labels: Weak / Fair / Strong / Very strong. `MODEL_FAST` writes a 1-line rationale.
5. **`ai/draft_complaint.py`** (`MODEL_SMART`) → `EmailDraft{subject, body, cited_refs[], attachments[], demand, deadline_date}`.
   - Subject: `Grievance: Refund of ₹4,299 not received | Order <id> | Ticket <id>`.
   - Body sections: facts (dated), attempts made, the specific demand, the legal basis (**only** passed-in verified refs), the deadline (**computed in code** and passed in), and the next step if unresolved.
   - Tone: firm, polite, specific, under 220 words, no threats, no fabricated facts.
6. **`ai/classify_reply.py`** (`MODEL_FAST`) → `ReplyAnalysis{category (acknowledged | deflection | info_requested | resolution_offered | partial_resolution | rejected | auto_reply), ticket_id, promised_date, offered_amount_inr, requested_info[], is_templated, templated_signals[], summary_hinglish}`.
   It is combined with a deterministic check: no date AND no amount AND no concrete action ⇒ deflection.
7. **`engine/policy.py`**: a pure-function state machine `(case, latest_event, now) → Decision{action, level, reason, requires_approval}`.
   - After sending L2: start `ack_48h` and `resolve_30d` deadlines.
   - `deflection` (1st) → firm follow-up citing the deadline. (2nd) or `ack_48h` breached → escalate to the next level.
   - `info_requested` → auto-fill from facts; if something is missing, ask the user in chat, then draft a reply.
   - `resolution_offered` with amount ≥ demand → ask the user to confirm receipt → RESOLVED.
   - `partial_resolution` → counter with the remaining amount.
   - `rejected` → escalate.
   - L3 exhausted → L4: generate the NCH-ready complaint text + link (user files it). Then L5: draft for the consumer commission.
   - Every decision writes an **Event with a human-readable `reason`** ("No date, no amount, no ticket: template reply detected. Escalating to Nodal Officer as per 48h rule.").
8. **`ai/draft_escalation.py`**: same rules as step 5, plus a reference to the previous email thread and its dates.

**Safety rules (non-negotiable):**
- Real (non-demo) recipients **always require user approval** before sending.
- Autopilot may auto-send only to addresses in `AUTOPILOT_ALLOWLIST` (the demo company).
- `SEND_ENABLED=false` blocks all sends (dry-run).
- Never send to `email: null` or `verified: false` recipients. The UI shows "Verify contact" instead.

---

## 8. Demo mode (must be bulletproof)

- **Demo company bot** (`demo/company_bot.py`): polls `DEMO_COMPANY_EMAIL` every 5s. For each new thread it replies after `DEMO_REPLY_DELAY_SECONDS` **in the same thread** (In-Reply-To/References):
  1. To the complaint: templated deflection ("We regret the inconvenience caused. Your concern has been forwarded to the concerned team and will be addressed at the earliest.").
  2. To the follow-up: a second deflection with a new ticket number but still no date.
  3. To the nodal escalation: a resolution offer ("Refund of ₹4,299 has been initiated. Reference RFN-…, credited in 5–7 working days.").
- **Demo clock:** a `⏩ +48h` button adds an offset to "now" everywhere (deadlines, policy). It's visibly labelled "Demo clock" in the UI.
- **Inject reply:** `Ctrl+Shift+R` inserts the next scripted company reply locally (for when email is slow).
- **Replay cache:** all LLM outputs are cached, so a rerun of the sample case is instant and identical.
- **3 sample cases** (one click): ShopKart refund ₹4,299 (the hero case), a food-delivery wrong item ₹612, and an airline cancellation refund ₹8,940 (draft only, no contact verified).
- **Reset demo:** a button that clears demo cases and the demo inbox state.

---

## 9. UI design system (judges notice this first; treat it as a top priority)

**Direction:** calm, premium, trustworthy. Think **Linear × Stripe × a modern Indian fintech.** Lots of whitespace, crisp typography, one accent colour. It must not look like a template.

- **Font:** Geist Sans (fallback Inter). `tabular-nums` for money and countdowns. Sizes: 13/14 body, 20–24 headings. Weights 400/500/600 only.
- **Colours:** neutral zinc/stone base, white cards, subtle borders (`zinc-200`), soft shadows. **One brand accent: deep indigo `#4338CA`** (buttons, active states, brand mark). Status: green = resolved/met, amber = waiting/running, red = deflection/breached, blue = info. Minimal gradients (only a faint one in the empty-state hero).
- **Brand:** wordmark "Shikayat" + a small shield-with-checkmark icon (lucide `ShieldCheck`). Custom favicon. Page title "Shikayat: AI that fights customer care for you".
- **Layout (desktop, three columns):**
  - **Left (260px):** Cases list. Each item shows company logo initial, title, ₹ amount, status pill, and the next deadline ("ack due in 41h"). Top: "+ New case" button. Bottom: "₹ recovered" counter.
  - **Centre:** a **messenger-style chat**. User bubbles hold screenshots and the voice note waveform; Shikayat bubbles use friendly Hinglish ("Case ready hai. Bhej doon?"). Action buttons sit inline in the bubbles.
  - **Right (420px): Case Board.**
    1. Facts card: company, order ID, amount, dates; each field has a confidence dot, and missing info is shown as amber chips.
    2. Strength meter.
    3. **Escalation ladder stepper** (L2 → L5) showing the current level.
    4. **Deadline countdowns**, ticking live.
    5. **Timeline**: events with actor icons (AI / You / Company / System) and an expandable "why" for every AI decision.
- **AI "thinking" state:** a step indicator ("Reading screenshots → Understanding the voice note → Finding the right officer → Drafting complaint") with checkmarks. Never a bare spinner.
- **Email preview dialog:** looks like a real email client (From / To / Subject / body). Legal citations and the deadline date are highlighted. Buttons: "Edit", "Approve & send".
- **Empty state:** a centred card: "Kya hua? Screenshot bhejo ya bolo." + 3 sample-case chips + a drag-and-drop zone + a mic button.
- **Onboarding (first run, 3 short steps):** "1. Send evidence → 2. Approve the complaint → 3. Shikayat follows up until you're paid." Plus a privacy note ("Emails go from *your* mailbox. Nothing is sent without your approval.").
- **Motion:** timeline items slide/fade in over 200ms, countdown digits tick, a status pill pulses briefly on change. Subtle only.
- **Feedback:** `sonner` toasts for every action. Skeletons while loading. Errors are friendly, with a retry button. Never a blank screen or raw stack trace.
- **Responsive:** on screens under 1024px, the right panel becomes a tab ("Chat | Case").
- **Quality bar:** every screen must be screenshot-ready for slides. No lorem ipsum, no default Next.js assets, no console errors, contrast ≥ 4.5:1, visible focus states.

---

## 10. Evaluation (shown on `/proof` and in the slides)

- `eval/cases/*.json`: **20 cases** modelled on common public complaint patterns (refund delays, wrong items, cancellations, overcharges, non-delivery). Paraphrased, synthetic details, **no real personal data.**
- Ground truth per case: company, issue_type, amount_inr, order_id, key dates, correct escalation target (role + email from companies.json), applicable verified legal ref, correct deadline date.
- **Baseline:** one call to `MODEL_SMART`: "Write a complaint email to the company about this issue", with the same inputs.
- **Shikayat:** the full pipeline.
- **Metrics (deterministic checks where possible):** facts extracted correctly (%), correct recipient/role (%), only verified legal refs cited and cited correctly (%), deadline date correct (%), explicit demand present (%), hallucinated facts (count), cost and latency per case.
- Output: `eval/results/<timestamp>.json` + a markdown table printed to the console + rendered on `/proof` with a clean bar chart.

---

## 11. Engineering rules

- Python: type hints everywhere, Pydantic models, small functions, `pytest` for the engine (policy, deadlines, strength) and the parsers.
- TS: strict mode, typed API client (`lib/api.ts`), no `any`.
- Before saying "done": `make test` and `make build` pass.
- Conventional commits (`feat:`, `fix:`, `chore:`). Commit after each green step.
- Secrets only in `.env`, never committed. Keep `.env.example` updated.
- `Makefile` targets: `dev`, `test`, `build`, `eval`, `docker`, `deploy`.
- Logging: structured, one line per event. Never log full email passwords or API keys.

---

## 12. Definition of done (the demo must do all of this, live, in under 3 minutes)

1. Click the sample case (or upload a screenshot + voice note) → facts appear with confidence → strength "Strong".
2. Email preview → Approve & send → it really arrives in the ShopKart demo inbox.
3. Within ~20s, the templated reply arrives → classified as **DEFLECTION** with signals shown → firm follow-up drafted and auto-sent (allowlisted).
4. The second deflection or `⏩ +48h` → **escalated to the Nodal Officer**, with the reason shown.
5. A resolution offer arrives → the user confirms → **RESOLVED**, "₹4,299 recovered".
6. `/proof` shows baseline vs Shikayat numbers.
7. Works on the deployed HTTPS URL **and** offline via replay cache + inject.

---

## 13. README requirements (the first thing the screening team reads)

1. Line 1: the one-line pitch. Line 2: a GIF of the hero flow. Line 3: the headline proof number.
2. "Why": the 30.7 hours fact + the 48h/1-month legal rule.
3. "How it works": a pipeline diagram (ASCII or Mermaid) highlighting the **deterministic policy engine + LLM understanding** split.
4. "AI-native, not a wrapper": vision extraction, structured outputs, reply classification, policy engine, evals.
5. Safety: human approval, allowlisted autopilot, no invented contacts or laws.
6. Run locally (3 commands), env vars, the deployed link, the demo video link.
7. "Built solo in 26 hours at Builders 2026 (OpenAI × Equal AI)".
