# Deployment

How this fork is deployed at <https://bracket.ai1to1.com>.

## Stack

```
browser ──TLS──▶ Cloudflare (edge cert for *.ai1to1.com)
                     │  proxied DNS record  bracket → origin
                     ▼
            nginx :443  (deploy/nginx/bracket.ai1to1.com.conf)
                     │  reverse proxy
                     ▼
            bracket container :8400  (docker compose, build: .)
                     │
                     ▼
                 postgres
```

The frontend is built with a **relative** API base (`VITE_API_BASE_URL=/api`, see
`Dockerfile`), so the same image works at `http://localhost:8400` and behind any
reverse-proxied host without rebuilding.

## 1. Run the app

```bash
docker compose up -d --build      # builds frontend (with the custom changes) + backend
```

Serves on `:8400`. Default admin login: `test@example.org` / the password baked
into the image config.

## 2. nginx reverse proxy

Copy the vhost into nginx and reload (the cert is the existing `ai1to1.com`
Let's Encrypt cert; Cloudflare runs in "Full" SSL mode so the origin cert does
not need to list the subdomain):

```bash
sudo cp deploy/nginx/bracket.ai1to1.com.conf /etc/nginx/conf.d/
sudo nginx -t && sudo systemctl reload nginx
```

DNS: a Cloudflare (proxied) record for `bracket` must point at this origin.

## 3. Create users

```bash
docker exec bracket uv run --no-dev ./cli.py register-user \
  --email <email> --password <password> --name <name>
```
