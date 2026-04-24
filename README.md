# Governor Chatbot Service

Self-hosted conversational AI for TrueSight DAO governors. Runs on EC2, proxies to Kimi (Moonshot AI) for inference, and executes approved actions.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  GitHub (TrueSightDAO/governor_chatbot_service)             │
│  ├── .github/workflows/refresh-governors.yml  (cron)        │
│  ├── governors.json                           (committed)   │
│  └── app/                                                   │
└──────────────────────────┬──────────────────────────────────┘
                           │ raw.githubusercontent.com
┌──────────────────────────▼──────────────────────────────────┐
│  EC2 (us-east-1, self-hosted)                               │
│  ├── FastAPI service (app/main.py)                          │
│  ├── Kimi API client (app/kimi_client.py)                   │
│  ├── Governor registry (app/governor_registry.py)           │
│  │   └── Fetches governors.json from GitHub raw URL         │
│  │   └── Caches in memory (TTL: 5 min)                      │
│  ├── Context loader (app/context.py)                        │
│  │   └── Reads agentic_ai_context files locally             │
│  └── scripts/sync_context.py (cron every 15 min)            │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS
┌──────────────────────────▼──────────────────────────────────┐
│  BROWSER (Governor at dapp.truesight.me/chat.html)          │
│  ├── Signs messages with RSA keypair (WebCrypto)            │
│  └── Sends {payload, signature} to EC2 /chat                │
└─────────────────────────────────────────────────────────────┘
```

## Phases

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Read-only Q&A with full workspace context | **In progress** |
| 2 | DAO `[CONTRIBUTION EVENT]` compilation + submission | Scaffolded |
| 3 | Code change assistant (read code, create PRs) | Planned |
| 4 | Controlled deploy with heavy safeguards | Future |

## Quick Start (Local)

```bash
cd governor_chatbot_service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — add KIMI_API_KEY at minimum
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Service runs at `http://localhost:8000`.

## Context Sync

```bash
python3 scripts/sync_context.py
```

Or set up cron:
```cron
*/15 * * * * cd /opt/governor_chatbot && python3 scripts/sync_context.py
```

## DApp Page

The chat UI lives in `dapp/chat.html` (static HTML/JS on GitHub Pages). It signs messages with the governor's existing RSA keypair and sends them to this service.

## Governor Registry

The governor registry is a **centrally managed JSON file** (`governors.json`) that lives in this repo and is refreshed automatically via GitHub Actions.

### How it works

1. **Source of truth:** The Main Ledger Google Sheet tab **"Contributors contact information"** (or a dedicated "Governors" tab).
2. **Refresh workflow:** `.github/workflows/refresh-governors.yml` runs daily at 06:00 UTC.
   - Reads the Sheet via service account
   - Filters rows where Status == "Governor" and Public Key is non-empty
   - Writes `governors.json`
   - Commits and pushes if changed
3. **EC2 consumption:** The FastAPI service fetches the canonical file via:
   ```
   https://raw.githubusercontent.com/TrueSightDAO/governor_chatbot_service/main/governors.json
   ```
   - Cached in memory for 5 minutes (configurable via `GOVERNORS_CACHE_TTL`)
   - Falls back to local `governors.json` if GitHub is unreachable
   - Falls back to **permissive mode** (empty list = allow all) in dev

### Adding a new governor

Option A — **Sheet-first** (recommended):
1. Add the governor's row to the Main Ledger "Contributors contact information" tab
2. Set **Status** column to `Governor`
3. Paste their **Public Key** (SPKI base64 from DApp localStorage) into the Public Key column
4. Wait for the next scheduled refresh (or trigger manually via GitHub Actions UI)

Option B — **Manual** (emergency):
1. Edit `governors.json` directly in this repo
2. Add an entry:
   ```json
   {
     "public_key": "AAAAC3NzaC1lZDI1NTE5AAAAI...",
     "name": "New Governor",
     "email": "gov@truesight.me",
     "status": "Governor"
   }
   ```
3. Commit and push

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Service health + governor count |
| GET | `/governors` | JWT | List governors (keys redacted) |
| POST | `/governors/refresh` | JWT | Force cache refresh |
| POST | `/refresh-context` | JWT | Rebuild system prompt |

### Required secrets for the workflow

| Secret | Purpose |
|--------|---------|
| `GOOGLE_CREDENTIALS_JSON` | Service account with Sheets read access to Main Ledger |
| `ORACLE_ADVISORY_PUSH_TOKEN` | PAT with `contents:write` on this repo |

## Environment Variables

See `.env.example` for full list.

### Required for Phase 1

| Variable | Description |
|----------|-------------|
| `KIMI_API_KEY` | Moonshot AI API key |
| `JWT_SECRET` | HS256 secret for session tokens |

### Optional for governor registry

| Variable | Default | Description |
|----------|---------|-------------|
| `GOVERNORS_RAW_URL` | `https://raw.githubusercontent.com/TrueSightDAO/governor_chatbot_service/main/governors.json` | Override the canonical registry URL |
| `GOVERNORS_CACHE_TTL` | `300` | Cache TTL in seconds |
| `STATIC_GOVERNORS_JSON` | — | Local fallback file path |

### Required for Phase 2

| Variable | Description |
|----------|-------------|
| `GITHUB_PAT` | Fine-grained PAT for PR creation |
| `EDGAR_API_TOKEN` | Edgar API token for submissions |

## Deployment (EC2)

1. Provision EC2 in **us-east-1** (Virginia), t3.micro minimum, t3.small recommended
2. Security group: ports 22 (SSH) and 8000 (service)
3. Install Python 3.11+, git
4. Clone this repo to `/opt/governor_chatbot`
5. `cp .env.example .env` and fill secrets
6. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
7. `python3 scripts/sync_context.py`
8. Run with systemd:
   ```ini
   # /etc/systemd/system/governor-chatbot.service
   [Unit]
   Description=TrueSight DAO Governor Chatbot
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/opt/governor_chatbot
   ExecStart=/opt/governor_chatbot/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
   Restart=always
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```
9. Enable and start: `sudo systemctl enable --now governor-chatbot`
10. Place nginx or ALB in front for HTTPS termination

## SSH Tunnel for Local Testing

If the EC2 is not publicly exposed on 8000:

```bash
ssh -i ~/.ssh/agentic_ai_github/id_ed25519 -L 8000:localhost:8000 ubuntu@<EC2_IP>
```

Then open `dapp/chat.html` locally and set:
```js
localStorage.setItem('governorChatApiUrl', 'http://localhost:8000');
```

## Security Notes

- EC2 **never** stores governor private keys. Only verifies signatures.
- `.env` is gitignored. Rotate secrets if exposed.
- Restrict `CORS_ORIGINS` to `https://dapp.truesight.me` in production.
- Use Redis for nonce cache and session store in production.
- Governor registry is public (raw GitHub URL) but contains only **public keys** — safe by design.

## License

Same as TrueSight DAO workspace.
