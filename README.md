Forward a screenshot, rant in a voice note, and walk away. Shikayat files the complaint with the right officer, tracks deadlines, reads replies, catches stalling, and escalates toward a refund.

Current milestone: application scaffold. Case handling, email sending and AI evaluation are pending. Demo GIF, proof numbers, deployment and video links will be added after verification.

## Run locally

Requires Python 3.11 (via [uv](https://docs.astral.sh/uv/)), Node.js 20.9+ and npm.

```sh
cp .env.example .env
make setup
make dev
```

Open [localhost:3000](http://localhost:3000). FastAPI runs on port 8000; the frontend proxies `/api/*` in development. No credentials are needed for the scaffold.

```sh
curl http://localhost:8000/api/health
curl -N http://localhost:3000/api/events
make test
make build
```

Health returns `{"status":"ok"}`. SSE sends a `ping` event every 15 seconds. `make test` runs the backend smoke test, ESLint and TypeScript checks. `make build` creates `frontend/out`; restart FastAPI after building to serve the export at [localhost:8000](http://localhost:8000).

## Architecture

```mermaid
flowchart LR
    Browser[Next.js static UI] --> API[FastAPI REST + SSE]
    API --> DB[(SQLite / SQLModel)]
    API -. planned .-> AI[LLM: understand evidence and replies]
    AI -. typed facts .-> Policy[Deterministic deadlines and policy]
    Policy -. approval .-> Mail[SMTP + IMAP]
```

`backend/app` contains API, AI, engine, mail and demo packages. SSE uses a bounded, in-process pub/sub and requires **one backend worker**. SQLite lives in `var/shikayat.db`. Settings read the project-root `.env`; API keys and passwords use secret fields. The default transcription model is retained from the brief and must be verified before implementing API calls. No OpenAI calls are made yet.

## Data and safety

`data/companies.json` contains fictional ShopKart and the 25 specified real companies. All real contacts and unverified URLs are `null`. ShopKart uses `email_env: DEMO_COMPANY_EMAIL`; `load_companies()` resolves the configured address at runtime. Missing email still means no recipient. Legal seeds remain unverified with null source URLs, so none are eligible for citation yet.

The planned sending boundary requires approval for real recipients, demo-only allowlisted autopilot, verified non-null addresses and a global `SEND_ENABLED` switch. Email sending is not implemented in this scaffold.

## Environment

See `.env.example` for model, budget, mailbox and demo settings. `DATABASE_URL` can override SQLite's default path, and `FRONTEND_DIST` can override the static-export directory. Do not commit `.env`.

## Production

```sh
make docker
docker run --rm --env-file .env -p 127.0.0.1:8000:8000 -v shikayat-data:/app/var shikayat
```

The image builds Next.js then copies its export into the Python runtime. On EC2, set `DOMAIN` to your instance's actual `<ip>.sslip.io` hostname and run Caddy with the supplied `Caddyfile`. Point DNS at the instance and allow inbound ports 80/443; Caddy proxies to the local container with SSE flushing. HTTPS and Docker deployment require verification on the target host. `make deploy` currently prints this prerequisite; it does not provision infrastructure.

`make eval` is a placeholder reporting that evaluation is pending; no results or performance claims are fabricated.

## Next

Implement deterministic deadlines, strength and policy, then evidence intake and structured AI extraction. The target is a product built solo in 26 hours at Builders 2026 (OpenAI × Equal AI). Code freeze: **22 November 2026, 2:00 PM IST**.

## Mock UI walkthrough

The frontend now runs entirely on typed fixtures in `frontend/lib/mock.ts` and the provisional response contracts in `frontend/lib/types.ts`. Choose ShopKart, review/edit the email, approve the mock send, then use **Simulate next** for deflection, escalation and the offer. Confirm receipt in chat to close the case. **+48h** advances the visible demo clock; reset clears the in-memory cases. All delivery and recovery are explicitly simulated. Refresh resets the case workspace; onboarding dismissal is remembered locally.

Image attachments and MediaRecorder voice notes stay in the browser. Uploaded evidence is not extracted yet; choose a sample for the scripted journey. Microphone recording needs localhost or HTTPS and permission. Legal citations are omitted until their sources are verified. These TypeScript contracts must be aligned with future case API routes when those routes are implemented.
