# Hosting the Toggle Wars preview

The `render.yaml` blueprint creates a free Docker web service from this repository. Connect the repository in Render, select the blueprint, and supply `OPENAI_API_KEY`, `ADMIN_PASSCODE`, and the Flagsmith **client-side environment key** through Render's secret fields. Do not commit these values. Set no Gmail credentials. The blueprint disables sending and enables the labelled simulation tools; it is a preview, not a production deployment.

Render's free filesystem is ephemeral: cases, uploaded evidence, and the local cost log disappear on restart or after the service sleeps. It may take about a minute to wake after inactivity. Use only fictional evidence. The application's `BUDGET_USD` limit relies on that local cost log and therefore resets when storage is lost; set a separate spending limit with the OpenAI account provider before making this endpoint public. API usage may incur charges.

The Flagsmith results shown in the app are synthetic test traffic and are not evidence of real-user conversion or a winning variant. The hosted service needs network access to Flagsmith and OpenAI for the respective live integrations. Without an OpenAI key the full case-understanding workflow is unavailable.
