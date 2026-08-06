---
source: grok-web
date: 2026-08-06
type: ops
topics: [website, dashboard, gemini, cloud-run]
title: Dashboard SPA asset fix landed (needs Cloud Run deploy)
---

# Dashboard SPA asset fix — code on main, deploy pending

**Repo:** `arigatoexpress/sapphire-alpha-dashboard` @ `5ed4058`

## Root cause

Mission Control HTML at `/dashboard` referenced `/assets/dashboard-*.js`.
Those assets 404'd into the Next marketing catch-all (**HTML as module**) → blank page (~701B shell).

## Fix

1. Vite `base: '/dashboard/'`  
2. Backend serves real `frontend/dist` files for `/dashboard/{path}`  
3. Harden `/assets/{path}` to never return marketing HTML  

## Gemini / Cloud Shell next

```bash
cd ~/sapphire-alpha-dashboard && git pull
# build + deploy with NO traffic shift first
# gcloud run deploy ... --no-traffic --tag=spa-fix
# curl tag URL /dashboard and /dashboard/assets/*.js — expect JS MIME
# owner phrase before 100% traffic
```

Live site still on old revision until deploy.
