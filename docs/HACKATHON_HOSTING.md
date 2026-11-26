# Hosting the Toggle Wars preview

The `render.yaml` blueprint creates a free Docker web service from this repository. Supply `ADMIN_PASSCODE`, `OPENROUTER_API_KEY`, and the Flagsmith **client-side environment key** through Render's configuration fields. Do not commit these values. Do not configure an OpenAI key or Gmail credentials. The preview uses only `openrouter/free` for custom text and image processing, with no paid-model fallback. Availability and rate limits apply; voice transcription and web contact discovery are disabled. Built-in sample extraction uses labelled replay for reliability. This is a preview, not a production deployment.

Render's free filesystem is ephemeral: cases, uploaded evidence, and the local cost log disappear on restart or after the service sleeps. It may take about a minute to wake after inactivity. Use only fictional evidence. The application's `BUDGET_USD` limit relies on that local cost log and therefore resets when storage is lost; it is not a reliable hard spending cap.

The Flagsmith results shown in the app are synthetic test traffic and are not evidence of real-user conversion or a winning variant. The hosted service needs network access to Flagsmith and OpenRouter for the respective live integrations. OpenRouter routes requests to third-party models; use fictional case data when testing.
