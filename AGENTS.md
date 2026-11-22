# Shikayat: evaluator run guide

Shikayat is an AI consumer advocate that turns evidence into a complaint and tracks replies.
It distinguishes acknowledgment from resolution using reply forensics and a deterministic policy engine.
The user reviews actions; simulated messages in evaluator mode never send email. Live site: https://54-242-22-145.sslip.io

## Requirements

Use Python **3.11** (tested with 3.11.14), Node.js **20.20.2** or **22** (Docker image uses 22), npm and `curl`. Docker Engine **28.4.0** with Compose v2 is optional. Python dependencies are pinned in `backend/requirements.txt`; JS dependencies are locked in `frontend/package-lock.json`. An OpenAI API key with access to the configured models is needed; API calls incur charges. If a model is unavailable to your key, set `MODEL_SMART`, `MODEL_FAST`, and verified prices accordingly. `make eval` has a separate $5 guard.

## Configuration

Only `OPENAI_API_KEY` and `ADMIN_PASSCODE` are required for this evaluator configuration. Never put real credentials in source control. Gmail credentials are not required and should be omitted for evaluation.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | empty | OpenAI API access |
| `ADMIN_PASSCODE` | Yes | empty | Local owner/admin tools |
| `MODEL_SMART` | No | empty | Vision/extraction and drafting model; set in evaluator example |
| `MODEL_FAST` | No | empty | Classification model; set in evaluator example |
| `TRANSCRIBE_MODEL` | No | `gpt-transcribe` | Audio transcription model |
| `MODEL_RATES_JSON` | No | `{}` | Required configured model prices for cost/budget accounting |
| `BUDGET_USD` | No | `100` | Total logged OpenAI budget cap |
| `DEMO_MODE` | No | `true` | Enable owner simulation controls |
| `REPLAY_MODE` | No | `false` | Replay sample extraction; real reply classification still uses OpenAI |
| `SEND_ENABLED` | No | `true` | Global send switch; MUST be `false` for evaluation |
| `PUBLIC_DEMO` | No | `false` | Restricts direct sends on public deployments |
| `USER_EMAIL`, `USER_EMAIL_APP_PASSWORD` | No | empty | Gmail sender and inbox poller; omit for evaluator mode |
| `DEMO_COMPANY_EMAIL`, `DEMO_COMPANY_APP_PASSWORD` | No | empty | Sandbox Gmail bot; omit for evaluator mode |
| `AUTOPILOT_ALLOWLIST` | No | empty | Addresses permitted for automatic follow-up |
| `DEMO_REPLY_DELAY_SECONDS` | No | `5` | Sandbox bot delay |
| `GRIEVANCE_FOLLOWUP_LIMIT`, `NODAL_FOLLOWUP_LIMIT` | No | `3`, `2` | Follow-up limits per level |
| `MIN_OUTBOUND_INTERVAL_HOURS`, `DEMO_OUTBOUND_INTERVAL_SECONDS` | No | `72`, `10` | Send spacing |
| `MAX_OUTBOUND_PER_CASE` | No | `8` | Send cap |
| `DATABASE_URL` | No | `sqlite:///.../var/shikayat.db` | SQLite location |
| `FRONTEND_DIST` | No | `frontend/out` | Static frontend export path |

## Evaluator mode: no Gmail, no sending

Create `.env` with the following exact settings, replacing only the two angle-bracket values with your own. The price table is for these specific models; check current pricing before changing models. Do not use production credentials.

```dotenv
OPENAI_API_KEY=<your-openai-api-key>
ADMIN_PASSCODE=<choose-a-local-passcode>
MODEL_SMART=gpt-5.4
MODEL_FAST=gpt-5.4-mini
MODEL_RATES_JSON={"gpt-5.4":{"input":2.5,"output":15},"gpt-5.4-mini":{"input":0.75,"output":4.5}}
BUDGET_USD=5
DEMO_MODE=true
REPLAY_MODE=true
SEND_ENABLED=false
PUBLIC_DEMO=false
```

Simulation is deliberately labelled and does **not** send a complaint or receive Gmail. The ShopKart sample's extraction may use replay; free-text uploads, reply classification and drafts call OpenAI. The owner `/admin/` panel can start simulated tracking, inject scripted or custom replies and advance the simulated clock. These tools are limited to the ShopKart sample. Never send to real companies while evaluating.

## Install, build and run

From the repository root, with Python 3.11 and Node installed:

```sh
python3.11 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000/ and http://localhost:8000/admin/. Enter the `ADMIN_PASSCODE` you chose above. In another terminal:

```sh
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

Expected JSON has `"status": "ok"`, a dynamic `instance_id` and `pid`, and `workers`: `inbox_poller` and `demo_bot` have `enabled: false`, `deadline_ticker` has `enabled: true`. Idle Gmail workers log that they are disabled. Ctrl-C stops the server.

Optional Docker Compose alternative (run instead of the venv/server commands, with the same `.env`):

```sh
docker compose -f docker-compose.evaluator.yml up --build
# open http://localhost:8000/; stop with Ctrl-C
```

Data persists in a Docker volume. `docker compose -f docker-compose.evaluator.yml down` stops it. `make test` runs backend tests, lint and type checking; `make build` builds the UI. `make eval` runs a NEW paid 20-case evaluation (no Gmail; results in `eval/results/`); do not run it if you only want to inspect existing measurements at http://localhost:8000/proof/.

## Four journeys

The following commands use `curl`, Python and a local cookie jar. Run from the repository root in a separate shell while the server is running. `PASSCODE` must match your own local `.env`; the cookie jar contains a session secret and should not be shared. An OpenAI call can take time. Copy each block into the same shell.

```sh
BASE=http://localhost:8000
read -rs -p 'Local ADMIN_PASSCODE: ' PASSCODE; echo
curl -sS -c /tmp/shk-cookies -H 'Content-Type: application/json' \
  -d "$(PASSCODE="$PASSCODE" .venv/bin/python -c 'import os,json; print(json.dumps({"passcode":os.environ["PASSCODE"]}))')" "$BASE/api/admin/login"
unset PASSCODE
# Expected: {"admin":true}
```

### J1: new case with text and screenshot

UI: New case → upload `samples/shopkart_order.png`, type “ShopKart refund of ₹4,299 for order SK-1042 has not arrived” → submit. The fictional screenshot is sample data and cannot be sent to a real company.

```sh
curl -sS -b /tmp/shk-cookies -F 'text=ShopKart refund of ₹4,299 for order SK-1042 has not arrived.' \
  -F 'images=@samples/shopkart_order.png;type=image/png' "$BASE/api/cases" > /tmp/shk-j1.json
.venv/bin/python -c 'import json; x=json.load(open("/tmp/shk-j1.json")); print(x["id"],x["facts_json"]["company_name"],x["mode"])'
```

Expected: a case ID, extracted company and `live` mode; extraction reads both the text and screenshot. User-provided text and image may disagree; inspect the evidence rather than assume either is correct.

### J2–J4 setup: sample with local simulated tracking

UI: select the ShopKart sample. Copy its case ID (visible in the URL `?case=...`); sign in at `/admin/`, enter it and select **Start simulated tracking**. This creates a local test record, not an email. For each journey below, run this setup again to start a fresh independent case:

```sh
curl -sS -b /tmp/shk-cookies -X POST "$BASE/api/cases/sample/shopkart" > /tmp/shk-sample.json
CASE=$(.venv/bin/python -c 'import json; print(json.load(open("/tmp/shk-sample.json"))["id"])')
curl -sS -b /tmp/shk-cookies -H 'Content-Type: application/json' -d "{\"case_id\":\"$CASE\"}" "$BASE/api/demo/start"
# Expected: {"status":"simulation_started","sent":false}
```

### J2: acknowledgment is not resolution

UI: in `/admin/`, enter the case ID and custom simulated reply `We regret the inconvenience. Your concern has been forwarded to the concerned team.`; click **Inject simulated reply**. Open the case: the Forensics card shows acknowledged, unresolved, and the policy's next action.

```sh
curl -sS -b /tmp/shk-cookies -H 'Content-Type: application/json' -d "{\"case_id\":\"$CASE\",\"text\":\"We regret the inconvenience. Your concern has been forwarded to the concerned team.\"}" "$BASE/api/demo/inject"
curl -sS -b /tmp/shk-cookies "$BASE/api/cases/$CASE/board" > /tmp/shk-board.json
.venv/bin/python -c 'import json; x=json.load(open("/tmp/shk-board.json")); print([(m["classification_json"].get("reply_type"),m["classification_json"].get("resolution_status")) for m in x["messages"] if m["direction"]=="in"]); print([(e["type"],e["title"],e["reason"]) for e in x["events"] if e["type"]=="decision"])'
```

Expected: acknowledged, unresolved; a follow-up is drafted for approval. The reply and outbound tracking are marked simulated.

### J3: partial offer

Run J2–J4 setup again. UI: inject `We offer a ₹200 coupon as a goodwill gesture.` Review the partial offer versus the ₹4,299 requested, and Accept/Counter controls.

```sh
curl -sS -b /tmp/shk-cookies -H 'Content-Type: application/json' -d "{\"case_id\":\"$CASE\",\"text\":\"We offer a ₹200 coupon as a goodwill gesture.\"}" "$BASE/api/demo/inject"
curl -sS -b /tmp/shk-cookies "$BASE/api/cases/$CASE/board" > /tmp/shk-board.json
.venv/bin/python -c 'import json; x=json.load(open("/tmp/shk-board.json")); print([(m["classification_json"].get("reply_type"),m["classification_json"].get("offered_amount_inr")) for m in x["messages"] if m["direction"]=="in"])'
```

Expected: `partial_offer`, offered amount 200, case needs a user decision.

### J4: dated promise and missed-promise draft

Run J2–J4 setup again. UI: inject `We will refund within 1 calendar day.`, then use **Advance clock** twice. Allow up to 10 seconds for the deadline ticker. The policy drafts a follow-up about the missed promise for approval; it does not claim that a missed promise alone requires a legal escalation.

```sh
curl -sS -b /tmp/shk-cookies -H 'Content-Type: application/json' -d "{\"case_id\":\"$CASE\",\"text\":\"We will refund within 1 calendar day.\"}" "$BASE/api/demo/inject"
curl -sS -b /tmp/shk-cookies -X POST "$BASE/api/demo/clock"
curl -sS -b /tmp/shk-cookies -X POST "$BASE/api/demo/clock"
sleep 12
curl -sS -b /tmp/shk-cookies "$BASE/api/cases/$CASE/board" > /tmp/shk-board.json
.venv/bin/python -c 'import json; x=json.load(open("/tmp/shk-board.json")); print([(e["type"],e["title"],e["reason"]) for e in x["events"] if e["type"] in ("promise","decision","draft","deadline")])'
```

Expected: promise event, breached promise deadline and a next-action draft citing the company's promise. Simulated clock affects only demo sample cases.

## Troubleshooting

1. `Configure ... model` or unknown model: check model access and `MODEL_SMART`, `MODEL_FAST`, `MODEL_RATES_JSON`; restart.
2. API key/budget errors: verify your key and `BUDGET_USD`; no secret values belong in logs or commits.
3. Port already in use: stop the existing process or run uvicorn with another port and change `BASE`.
4. 403/404 in `/admin` or cases: log in with the local passcode using the same browser/cookie jar; cases are isolated by visitor.
5. Simulation rejected: set `DEMO_MODE=true`, `SEND_ENABLED=false`, restart, use a fresh ShopKart sample and start simulated tracking before injecting. SMTP/IMAP are intentionally disabled without credentials.
