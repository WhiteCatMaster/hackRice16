# Deployment

Production is **https://exchangetreasurer.us**, a single Ubuntu 22.04 VPS.
This describes the server as last recorded on 2026-09-12. Verify on the box
before relying on any detail.

## Layout

```
                 :443 exchangetreasurer.us (nginx, Let's Encrypt)
                  ├── /api/  → 127.0.0.1:8000   fastapi.service  (uvicorn backend.api.app:app)
                  └── /      → 127.0.0.1:3000   nextjs.service   (npm run start in frontend/)
```

| Thing | Where |
|---|---|
| Checkout | `/var/www/myapi`, branch `main` |
| Python venv | `/var/www/myapi/venv` (untracked) |
| Cache | `/var/www/myapi/data/treasurer.db` (untracked) |
| API service | `fastapi.service`: `venv/bin/uvicorn backend.api.app:app` on `127.0.0.1:8000` |
| Web service | `nextjs.service`: `npm run start` in `frontend/` on `:3000` |
| nginx | `/etc/nginx/sites-available/default`; backups in `/root/nginx-default.bak-*` |

nginx redirects:
- Port 80 serves ACME challenges and redirects everything else to
  `https://exchangetreasurer.us` (301; 308 for `/api/`, which preserves POST).
- A default 443 server redirects any other name: `www`, the bare IP, and the
  `sslip.io` hostname.

**Redirects must target `exchangetreasurer.us`.** A redirect to the `sslip.io`
name once bounced real visitors away from the domain.

## What production actually serves

- There is **no root `.env`** on the server. The agent runs in scripted mode and
  approved transfers never reach Nessie.
- There is **no `frontend/.env.local`**, so the Next.js server renders pages
  from `mocks/`.
- nginx sends every `/api/` path to FastAPI, which **shadows the Next.js routes
  under `frontend/app/api/`**. Calls the browser makes itself (chat, transfer
  checks, affordability, confirm) therefore reach the live API and its cache.
  The server-rendered dashboard still comes from fixtures.

The contracts are identical, so this works. The two sides can still disagree:
the gap, alerts on an unarmed cache, and balances after an approval. To make
production fully live, set `TREASURER_API_BASE=http://127.0.0.1:8000` in
`frontend/.env.local`, rebuild, and restart.

## Deploying

On the server, in `/var/www/myapi`:

```bash
git --no-pager log -1 --oneline       # --no-pager: over ssh -tt, git log otherwise hangs in less
git pull --ff-only
(cd frontend && npm install && npm run build)   # npm here, not pnpm
systemctl restart fastapi nextjs
```

Then verify:

```bash
cat frontend/.next/BUILD_ID
curl -s https://exchangetreasurer.us/ | grep -o '"buildId":"[^"]*"'   # must match BUILD_ID
curl -s https://exchangetreasurer.us/api/health | python3 -m json.tool
```

In `/api/health`, `engine.engine_module` must be `"backend.engine"`, which
needs the venv on Python 3.13. The Ubuntu 22.04 system Python is older, so check
`venv/bin/python --version`.

## Pitfalls

- **A running process hides breakage.** A pull or a build changes nothing until
  the services restart. The venv and the database were once deleted under live
  processes, and it only showed on the next restart. Always restart and
  re-check health after deploying.
- **Missing venv or database:**

  ```bash
  python3 -m venv venv && venv/bin/pip install -r requirements.txt
  venv/bin/python -m seed.seed
  venv/bin/python -m seed.scenarios all
  ```

  `seed.reset_demo` also works if permitted.
- **Never pass `--push` on the server.** That path deletes objects in the shared
  Nessie sandbox.

## HTTPS

- Certbot (snap), lineage `exchangetreasurer.us`, covering
  `exchangetreasurer.us`, `www.exchangetreasurer.us` and the `sslip.io` name.
  Webroot is `/var/www/letsencrypt`.
- Renewal runs from `snap.certbot.renew.timer`, with deploy hook
  `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`.
- The certificate was registered without an email, so **no expiry warnings are
  sent**. Check `certbot certificates` occasionally.
- An older, unused `96-30-207-34.sslip.io` lineage still exists and renews.
