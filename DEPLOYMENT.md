# Deployment (P5)

Production stack: a reverse proxy (nginx) is the only public entry point,
routing `/` to the frontend and `/api/` to the backend — normally also
terminating HTTPS (sections 1 and 3 below), or plain HTTP only when that's
all you need yet (section 2 — e.g. a demo subdomain before a certificate
is ready). Postgres and Redis are never exposed outside the internal
Docker network — same as in the dev stack (`docker-compose.yml`), just
now also true for the backend and frontend containers themselves.

```
Internet ──▶ reverse-proxy (80/443, TLS) ──▶ frontend (static SPA, nginx)
                                          └─▶ backend (FastAPI, /api/*)
                                                 ├─▶ postgres (internal only)
                                                 └─▶ redis    (internal only)
```

## 1. Quick start — self-signed HTTPS, no domain needed

This is enough to test the whole stack locally (including HTTPS itself,
where a real domain isn't required) or to record the demo video before a
real domain is ready. Browsers will show a "not trusted" warning for the
certificate — expected, and irrelevant for local testing/recording.

```bash
cp .env.production.example .env.production
# edit .env.production: at minimum fill in SECRET_KEY, SECRETS_ENCRYPTION_KEY,
# POSTGRES_PASSWORD (generation commands are in the file's own comments).
# Leave DOMAIN=localhost for this quick-start path.

./deploy/nginx/generate-self-signed-cert.sh localhost

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Then open `https://localhost` (accept the browser's self-signed-cert
warning). Log in with the demo account: `admin@aquaresilience.demo` /
whatever `DEMO_ADMIN_PASSWORD` you set in `.env.production`.

`--env-file .env.production` is required on **every** command against
`docker-compose.prod.yml`, not just the first — see that file's own top
comment for why (this repo also has a dev `.env`, and Compose's variable
interpolation silently picks whichever `.env` it's told to use).

## 2. HTTP-only demo deploy (e.g. a subdomain, no certificate yet)

Use this when you want the real production stack — built images,
multi-worker backend, no `--reload`, no source bind-mounts, same hardening
as the TLS path below — reachable over plain HTTP on port 80, with no
certificate at all. Typical case: a demo subdomain (e.g.
`oneaquahealth.forkandfry.com` — adjust to whatever subdomain you're
actually using) that needs to be up quickly, before a certificate is
issued, or that already sits behind something else terminating TLS (a CDN
or load balancer in front of this server).

```bash
cp .env.production.example .env.production
# edit .env.production: DOMAIN=<your-subdomain>, e.g.
#   DOMAIN=oneaquahealth.forkandfry.com
# fill in SECRET_KEY, SECRETS_ENCRYPTION_KEY, POSTGRES_PASSWORD (same
# generation commands as section 1). LETSENCRYPT_EMAIL isn't used on this
# path — leave it blank.

docker compose -f docker-compose.prod.yml -f docker-compose.prod.http.yml \
  --env-file .env.production up -d --build \
  reverse-proxy backend frontend postgres redis
```

Point the subdomain's DNS A/AAAA record at this server's public IP
(propagation can take a few minutes to a few hours), then open
`http://<your-subdomain>` — no certificate warning, because there is no
certificate; this is plain HTTP, the same trust model as the local dev
stack (`docker-compose.yml`).

What `docker-compose.prod.http.yml` changes on top of the base file (see
that file's own top comment for the full mechanics): the reverse proxy
serves `deploy/nginx/nginx.http.conf.template` instead of the TLS
template — plain `listen 80`, no redirect, no HSTS header (that header
would be actively wrong to send over a connection that isn't actually
HTTPS) — and the backend's `CORS_ORIGINS` is set to `http://${DOMAIN}`
instead of `https://${DOMAIN}`, so the frontend's own API calls aren't
rejected over a scheme mismatch. The `certbot` service from the base file
is deliberately left out of the `up` command above — it only matters for
the TLS path.

Port 443 stays published by the base file in this mode (nothing
overridden there, on purpose — see the override file's own comment);
harmless, since nothing listens on it with this nginx config, so a
connection to it is simply refused rather than silently open to anything.

Switching this same deployment to TLS later, once a certificate is ready:
stop passing `docker-compose.prod.http.yml` and follow section 1 or 3
instead — same containers, same data (Postgres volume, demo account,
anything already ingested), no rebuild needed beyond the reverse proxy
picking up its normal TLS config.

## 3. Real domain + trusted certificate (Let's Encrypt)

Prerequisites: a domain whose DNS A/AAAA record already points at this
server's public IP (Let's Encrypt's HTTP-01 challenge needs that to
succeed — propagation can take a few minutes to a few hours depending on
your registrar), and ports 80+443 reachable from the internet.

```bash
cp .env.production.example .env.production
# Fill in DOMAIN=your-real-domain.example, SECRET_KEY, SECRETS_ENCRYPTION_KEY,
# POSTGRES_PASSWORD, and LETSENCRYPT_EMAIL.

# 1) Bootstrap with a self-signed cert so nginx has something to bind to —
#    it gets replaced by the real one in step 3.
./deploy/nginx/generate-self-signed-cert.sh your-real-domain.example

# 2) Bring the stack up. Port 80 is what proves domain ownership to Let's
#    Encrypt next, so this step must succeed first.
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build

# 3) One-off real certificate issuance. The `certbot` service's own default
#    entrypoint is the renewal loop (see docker-compose.prod.yml) — override
#    it back to the image's plain `certbot` binary for this one-off request,
#    so you see exactly what domain/email you're issuing for:
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm \
  --entrypoint certbot certbot \
  certonly --webroot -w /var/www/certbot \
  -d your-real-domain.example \
  --email you@example.com --agree-tos --no-eff-email \
  --deploy-hook /etc/letsencrypt/renewal-hooks/deploy/copy-to-nginx.sh

# 4) Pick up the real certificate (the deploy-hook already copied it into
#    deploy/nginx/certs/ — nginx just needs to re-read it):
docker compose -f docker-compose.prod.yml --env-file .env.production exec reverse-proxy nginx -s reload
```

From here, the `certbot` service (already running as part of the stack)
checks for renewal every 12h and re-runs the same deploy-hook automatically
— Let's Encrypt certs are valid 90 days and certbot only actually renews
within ~30 days of expiry, so this is normally a no-op. **nginx does not
auto-reload on a renewed file**, though: add a monthly cron entry on the
host running step 4's `exec ... nginx -s reload` command (a hackathon demo
window is far shorter than the 90-day validity, so this is a "for later"
concern, not a blocker for submission).

## 4. What's already hardened

- `ENVIRONMENT=production` makes the app refuse to start on the dev-only
  `SECRET_KEY`/`SECRETS_ENCRYPTION_KEY` defaults (`app/core/config.py`) —
  `.env.production.example` leaves both blank on purpose, with the
  generation command right there in the comments.
- `/docs`, `/redoc`, `/openapi.json` are disabled in production
  (`app/main.py`) — no API schema exposed publicly.
- Postgres/Redis: no host ports published; only reachable from other
  containers on the internal Docker network.
- Backend/frontend: no source bind-mounts (the image's own baked-in code
  runs, matching what's actually deployed) and no host ports published
  either — only the reverse-proxy container is publicly reachable.
- Backend runs multi-worker (`--workers 2`, no `--reload`) with
  `--proxy-headers` so it correctly trusts `X-Forwarded-Proto` from nginx.
- Reverse proxy: HTTP→HTTPS redirect, HSTS, `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, gzip.
- `.dockerignore` added for both `backend/` and `frontend/` — previously
  absent, meaning `backend/`'s 135MB `.venv/` and both directories' real
  dev `.env` files (the frontend one hardcoded to
  `http://localhost:8000/api/v1`, which would have been baked into the
  production JS bundle) were being copied straight into the build context.
- Fixed a pre-existing bug found during this hardening pass: the backend's
  Docker healthcheck was probing `/health/live`, a path that only exists
  under the versioned API prefix (`/api/v1/health/live`) — it had been
  silently failing (always 404) since it was written. A plain `/health`
  liveness route was added for exactly this (infra probes shouldn't need
  to know the API version), and both compose files' healthchecks now
  point at it. This one mattered here specifically: `docker-compose.prod.yml`
  gates `reverse-proxy` on `backend: condition: service_healthy` — with the
  old broken healthcheck, the whole production stack would have hung
  forever waiting for a backend that was actually fine.

## 5. What still needs your input before this is a "real" deployment

- **A production domain** (§12 of the progress tracker) — the quick-start
  above works with `DOMAIN=localhost` in the meantime.
- **Repository license** and **submission credentials** — unrelated to this
  deployment setup, tracked separately.
- This was built and validated without a live Docker daemon available in
  the sandbox this was developed in (`docker compose config`, `nginx -t`
  against the real template, and every shell script's syntax were all
  verified; a full `docker compose up` end-to-end run was not possible
  here). Run the quick-start above once on a machine with Docker to confirm
  the live build — flag anything that doesn't match this doc and it'll get
  fixed.
- Section 2's HTTP-only override (`docker-compose.prod.http.yml`) was
  verified the same way: `docker compose config` (confirms the merge —
  `CORS_ORIGINS` correctly becomes `http://${DOMAIN}`, the reverse-proxy
  volume correctly swaps to the HTTP template) and `nginx -t` against the
  rendered template (with the Docker-network-only hostnames `backend`/
  `frontend` swapped for `127.0.0.1` purely for this standalone syntax
  check — they resolve fine inside the real Compose network). Not yet run
  end-to-end against a live demo subdomain.
