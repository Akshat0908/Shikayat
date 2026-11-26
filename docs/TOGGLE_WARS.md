# Toggle Wars — Shikayat’s first-step experiment

**Entry:** Track 01, Test Something Real. **Deadline:** 29 November 2026, 8 PM IST. The current [official rules](https://www.wemakedevs.org/hackathons/flagsmith/rules) permit a head start and require Flagsmith to be central, a public repo, setup instructions and a working demo video. Shikayat existed before the event; the Flagsmith experiment, instrumentation and experiment page were built for Toggle Wars.

## The question

People arriving with a consumer complaint may not know what to do first. **Hypothesis:** a three-step introduction will increase the proportion of opted-in visitors who start a case compared with the original introduction. This is a hypothesis, not a measured result or a promise of improvement.

- **Control:** existing one-line explanation, “Send evidence → Approve → Shikayat follows up until you’re resolved.”
- **Guided:** “1. Share a screenshot or a few words. 2. Review your complaint. 3. Track the company’s reply.” The sample chips, input and safety rules remain the same.
- **Unit of randomisation:** a random experiment session identifier; a browser joining again in the same tab retains that identifier. It is not a case, email or user account identifier.
- **Primary metric:** occurrence of `case_started` after exposure — the user submits new evidence or chooses a sample. This is a start, not a completed or resolved complaint. Flagsmith deduplicates occurrence per identity.
- **Population:** visitors who explicitly select “Join the experiment” on the empty state. Report the opt-in nature and any selection bias. Non-participants see the original experience and no Flagsmith events are sent.
- **Design:** 100% of opted-in identities enter a 50/50 split, for one fixed experiment period. Report exposures and unique conversions per arm, conversion rates, uncertainty and the actual measurement dates; do not claim causation from a tiny sample or stop because one arm briefly leads.
- **Privacy and safety:** the experiment sends a random session ID, exposure variant, event names, SDK version and timestamps to Flagsmith. It does not send complaint text, screenshot contents, contact details, email addresses or case IDs. Network requests also disclose standard connection information, including the client IP address, to the configured Flagsmith service. The toggle does not change eligibility, sending, legal rules, or approvals. SDK errors fall back to the existing introduction.

## Configure real Flagsmith Experimentation

Prerequisites: a Flagsmith Cloud account or a self-hosted instance with Experimentation enabled and a connected warehouse. Follow the [official experimentation guide](https://docs.flagsmith.com/experimentation/run-an-experiment). SDK environment keys are public; **management API keys are secret** and must never be entered in the frontend or committed. Use a dedicated development environment for the event.

1. In Flagsmith, create the multivariate flag `shikayat_onboarding`. Set its control value and key to `control`; add the variation with value and key `guided`. Ensure the flag is enabled and variation keys are present.
2. Connect an experiment warehouse. Create an **occurrence** metric with event name `case_started`, higher is better.
3. Create an experiment using the flag and metric, 100% rollout and 50/50 control/guided split. Check the review page and start the experiment. A running experiment locks its flag settings.
4. Put the **client-side environment key**, not a management token, into `.env` as `FLAGSMITH_ENVIRONMENT_ID`. For self-hosting, also set `FLAGSMITH_API_URL` to the SDK API URL ending in `/api/v1/` and `FLAGSMITH_EVENTS_URL` to the event ingestion URL (when using the Flagsmith database, the instance URL ending `/api/`). Leave both empty for Flagsmith Cloud. Restart the backend.
5. Open the app, dismiss onboarding, and click **Join the experiment**. Starting a case records the conversion. Check exposures and events in the Flagsmith dashboard after ingestion. `/experiment/` explains the design; its local A/B preview does not send analytics or represent measured results.

The code reads the public SDK key from `GET /api/experiment/config`; the Next.js static build never needs a secret. Do not put an organisation or management token in this setting. If unconfigured or Flagsmith is unavailable, the app retains the control experience and explicitly reports the experiment is unavailable.

## Optional synthetic traffic — separate test environment only

Synthetic traffic validates the wiring; it is **not evidence of real user preference**. Create a second, dedicated Flagsmith environment and the same flag, occurrence metric, warehouse and experiment there. Never mix synthetic traffic with a real visitor experiment. Install frontend dependencies first, then set its SDK key in a shell variable and run:

```sh
export FLAGSMITH_SYNTHETIC_ENVIRONMENT_ID='<dedicated-test-environment-key>'
# Set FLAGSMITH_API_URL and FLAGSMITH_EVENTS_URL too only if self-hosting.
node frontend/scripts/simulate-flagsmith.mjs --ack-synthetic
```

The script creates 40 random synthetic identities by default (set `FLAGSMITH_SYNTHETIC_COUNT` to 1–200), uses Flagsmith’s official Node SDK to record exposures, and queues `case_started` with a 40% probability in **both** arms. Metadata and identifier prefix identify the traffic as synthetic. It flushes events on close. Queued counts are not proof of delivery; check the Flagsmith dashboard. Results from this deliberately modelled traffic do not support a claim that either design works better. The script requires an explicit acknowledgement, requires a primary `FLAGSMITH_ENVIRONMENT_ID` in the shell or project `.env`, and refuses to run when its test key equals that primary key. Distinct keys do not by themselves prove the environments are separate; verify the test environment in Flagsmith first.

## Recorded synthetic wiring check (26 November 2026)

A separate, explicitly synthetic Flagsmith experiment enrolled 100 scripted identities. The Flagsmith dashboard reported control **17/52 (32.7%)** and guided **16/48 (33.3%)** case starts, with a “collecting data” status. Both arms were generated with the same 40% probability. These are generated test observations, not real customer outcomes, and no winner is claimed. [Open the synthetic dashboard](https://app.flagsmith.com/project/56571/environment/4WAeDJFxNvKzMN9F5rjFLc/experiments/684) (owner sign-in required). The snapshot is in `data/flagsmith_synthetic_results.json`.

The separate Development visitor experiment was started on 26 November. One identity named as synthetic diagnostics was evaluated through `getExperimentFlag` during setup; an exposure was attempted in that environment and must be treated as test traffic if it appears in results. The app had not yet been deployed with the experiment at the time of this snapshot.

## Demo checklist

1. Show the real `/experiment/` page and explain the question, control, guided variant and opt-in privacy boundary.
2. Show the running experiment, its two flag values and occurrence metric in Flagsmith; use a test environment and clearly label any scripted traffic.
3. In Shikayat, join the experiment, show the assigned copy, and start a sample or upload a fictional screenshot. Never show or send a real consumer complaint.
4. Return to Flagsmith and show actual exposure and metric results. If there are not enough real observations, say so; do not manufacture a winner.
5. Record a short video of the above and include its public URL with the submission. Existing Shikayat demo footage predates this experiment and is not evidence of a Flagsmith experiment.
