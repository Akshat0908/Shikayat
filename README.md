Shikayat — your AI consumer advocate. It doesn't stop when customer care replies. It stops when your issue is actually resolved.

Share evidence, review a complaint, and track company replies with evidence-based forensics and a deterministic next-action policy. Verified contacts and your approval are required before a complaint is sent. ShopKart is a fictional sandbox merchant with automated replies for testing.

## Toggle Wars: one experiment, clearly measured

**Track 01 — Test Something Real.** Can a short, three-step introduction help people start a consumer case? Flagsmith assigns opted-in visitors to the original or guided introduction and measures the `case_started` occurrence event. Participation is optional; Flagsmith receives a random session identifier, exposure and case-start events, SDK version and timestamps, never complaint text, screenshots, email addresses or contact details. Like any web service, Flagsmith can receive network information such as the client IP address.

[Live app](https://shikayat-toggle-wars.onrender.com/) · [Experiment page](https://shikayat-toggle-wars.onrender.com/experiment/) · [Experiment design and setup](docs/TOGGLE_WARS.md) · [Existing AI evaluation](https://shikayat-toggle-wars.onrender.com/proof/)

**Status:** the Development visitor experiment is running in Flagsmith and the integration is live. A separate synthetic-only experiment recorded 100 test exposures and 33 simulated case starts; those are not real-user results. One diagnostic exposure was attempted in the Development experiment and must be treated as test traffic if it appears. No winner is claimed. Shikayat existed before Toggle Wars; the Flagsmith integration and experiments are new work for the event. The [organisers explicitly permit simulated traffic](https://www.wemakedevs.org/hackathons/flagsmith#tracks); the reported run is a wiring check, not evidence of user preference.

The public preview uses OpenRouter's free model router, not paid OpenAI calls. Free models can be unavailable or rate-limited and their extraction can be inaccurate: check all facts. Voice transcription, contact web search and email sending are disabled. Storage is temporary and can disappear on restart or inactivity; use fictional evidence only. See [preview hosting](docs/HACKATHON_HOSTING.md).

## Run locally

Requires Python 3.11, `uv`, Node.js and npm.

```sh
make setup
cp .env.example .env
make dev
```

Open [localhost:3000](http://localhost:3000). Configure the OpenAI models and mailbox settings in `.env` for live extraction and mail tracking. Run `make test` and `make build` to verify changes.

## Sending and tracking

Visitors use **Send from my email** to open a draft in Gmail or another mail app. The message contains a case tag and copies the configured tracking address. Confirm **I've sent it** after sending to start the applicable deadlines. A company replying only to the visitor may omit the tracking address; ask it to reply all or forward or paste the reply into the case. Shikayat prepares follow-ups for visitor review and sending.

Set `ADMIN_PASSCODE` in `.env` and restart to enable owner sign-in at `/admin`. Signed-in owners can approve direct sending through the configured Gmail mailbox and access sandbox controls. A passcode is never shipped by default. `PUBLIC_DEMO=true` does not grant direct SMTP access to visitors; direct sending requires the owner session. Automated follow-ups remain restricted to allowlisted sandbox recipients and owner-started cases. The `SEND_ENABLED` switch blocks sending, and sample-labelled evidence cannot be sent to a real company.

Cases are scoped to a browser visitor or the owner session. This is a prototype; use a dedicated test environment and synthetic evidence for public demonstrations.

## Evidence and safeguards

- Screenshot, voice and text inputs become case facts and an evidence ledger. Reply Forensics identifies acknowledgments, deflections and offers; the policy engine decides the next action with a recorded reason.
- Official-contact discovery searches company domains and requires confirmation before marking a contact verified. Customer support is labelled separately from a designated grievance officer.
- The 48-hour acknowledgment and one-month redressal rule is used only for covered e-commerce cases. Other configured sectors require review. NCH-ready text is a draft for the user to file.
- `/proof` labels illustrative evaluation results as sample data until measured results are available.

The app uses FastAPI, SQLite and a static-export Next.js frontend. Environment values and local case data must not be committed. See `.env.example` for configuration.
