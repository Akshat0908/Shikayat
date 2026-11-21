# Deploying Shikayat

The production stack is the Ubuntu EC2 instance at `54.242.22.145`, with Caddy providing HTTPS at https://54-242-22-145.sslip.io. Open inbound TCP ports 80 and 443 in the instance security group. The app is not exposed directly.

1. Keep the SSH key at `~/Desktop/Builders/shikayat-key.pem` (or set `SHIKAYAT_SSH_KEY`) and protect it with mode 400. `*.pem` and `.env` must remain ignored by Git.
2. Populate local `.env`, including a strong `ADMIN_PASSCODE`, both Gmail accounts, the API key, and the sandbox allowlist. Never commit or print it.
3. Run `make test` and commit the intended revision. `make deploy` archives **HEAD**, installs Docker/Compose if needed, securely copies `.env`, builds the image, and starts one application process. Uncommitted work is never deployed.
4. Check `https://54-242-22-145.sslip.io/api/health`, then sign in at `/admin` and verify the sandbox flow. Keep all other Gmail pollers stopped.

The production environment is stored separately at `/home/ubuntu/.config/shikayat/production.env` (mode 600); `PUBLIC_DEMO` and `DEMO_MODE` are forced true. The `app_data` volume keeps SQLite and evidence, while `directory_data` retains confirmed contacts. Caddy's named volumes retain certificates. Back up these volumes securely before replacing the server. A persistent directory volume keeps its existing company data across redeploys.

For later updates, commit and run `make deploy` again. To inspect service status without revealing configuration, SSH in and run `cd ~/shikayat/current && sudo docker compose -p shikayat ps`. To stop all workers, run `sudo docker compose -p shikayat stop app` there. Do not run a second app instance or local Gmail workers while production is running.
