# Trigger.dev — Amaris development setup

Project ref: `proj_csbqzfhbaihlazhevucz`.

This setup defines **one read-only, self-contained smoke-test task**: `amaris-development-heartbeat`. It does not deploy an AI agent or alter production resources.

## Developer steps

From `frontend/` (requires Node.js 24 per the current Amaris project):

```sh
npm install @trigger.dev/sdk@latest
npm install --save-dev @trigger.dev/build@latest
npx trigger.dev@latest login
# Add your development-only TRIGGER_SECRET_KEY to frontend/.env.local
npx trigger.dev@latest dev
```

In the Trigger.dev Development dashboard, find `amaris-development-heartbeat`, launch a test run with payload `{"message":"Amaris development connection test"}`, and confirm the completed output contains `"status":"ok"`.

**Important:** Regenerate and commit `frontend/package-lock.json` from a trusted machine before merging. This branch intentionally does not fabricate an npm lockfile. Package versions recorded as `latest` are placeholders until npm resolves them. Keep Trigger SDK, build and CLI versions aligned. Do not run `npm ci` or merge until the lockfile is synchronized and security/test checks pass.

## Security

Never commit `TRIGGER_SECRET_KEY`; do not place it in public Vite environment variables. Only use a development-environment key. Production services and existing Django/Render deployments remain unchanged. Running `dev` creates a development worker, **not** a production deployment.
