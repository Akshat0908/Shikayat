# Hosting the Toggle Wars preview

The `render.yaml` blueprint creates a free Docker web service from this repository. Connect the repository in Render, select the blueprint, and supply `ADMIN_PASSCODE` and the Flagsmith **client-side environment key** through Render's configuration fields. Do not commit these values. Do not configure an OpenAI key or Gmail credentials. The blueprint disables sending and enables the labelled replay tools; it is a preview, not a production deployment. Without an OpenAI key, custom case extraction, drafting and live reply analysis are unavailable; the sample's extraction uses prerecorded data.

Render's free filesystem is ephemeral: cases, uploaded evidence, and the local cost log disappear on restart or after the service sleeps. It may take about a minute to wake after inactivity. Use only fictional evidence. The application's `BUDGET_USD` limit relies on that local cost log and therefore resets when storage is lost; it is not a reliable hard spending cap.

The Flagsmith results shown in the app are synthetic test traffic and are not evidence of real-user conversion or a winning variant. The hosted service needs network access to Flagsmith and OpenAI for the respective live integrations. Without an OpenAI key the full case-understanding workflow is unavailable.
