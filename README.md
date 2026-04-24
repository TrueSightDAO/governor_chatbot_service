# Governor Chatbot Service

Self-hosted conversational AI for TrueSight DAO governors. Runs on EC2, proxies to Kimi (Moonshot AI) for inference, and executes approved actions.

## Architecture

- **FastAPI** service on EC2
- **Kimi API** for long-context inference (~200K tokens)
- **RSA signature auth** via existing DApp keypairs
- **JWT sessions** for continuity
- **Context sync** via git clone/pull of `agentic_ai_context`

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
python3 -m app.main
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

## Environment Variables

See `.env.example` for full list. Required for Phase 1:

- `KIMI_API_KEY` — Moonshot AI API key
- `JWT_SECRET` — HS256 secret for session tokens

Required for Phase 2:

- `GITHUB_PAT` — Fine-grained PAT for PR creation
- `EDGAR_API_TOKEN` — For governor registry queries and submissions

## Deployment (EC2)

1. Provision EC2 (t3.large recommended)
2. Install Python 3.11+, git, redis
3. Clone this service to `/opt/governor_chatbot`
4. `cp .env.example .env` and fill secrets
5. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
6. `python3 scripts/sync_context.py`
7. Run with systemd or supervisord:
   ```
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
8. Place nginx or ALB in front for HTTPS termination

## Security Notes

- EC2 **never** stores governor private keys. Only verifies signatures.
- `.env` is gitignored. Rotate secrets if exposed.
- Restrict `CORS_ORIGINS` to `https://dapp.truesight.me` in production.
- Use Redis for nonce cache and session store in production.

## License

Same as TrueSight DAO workspace.
