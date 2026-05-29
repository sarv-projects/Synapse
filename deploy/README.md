# Deploy

## Cloud Run (backend)

```bash
# Authenticate gcloud first
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Deploy (idempotent — re-run any time to redeploy with latest .env values)
PROJECT_ID=YOUR_PROJECT_ID REGION=us-central1 ./deploy/deploy_cloud_run.sh
```

What the script does:

1. Enables Run, Cloud Build, Artifact Registry, Secret Manager, Firestore APIs.
2. Reads `.env` and pushes one Secret Manager secret per key listed in
   `SECRET_KEYS` (e.g. `synapse-secrets-NEO4J_URI`). Each run adds a new version.
3. Grants the Cloud Run runtime SA `roles/secretmanager.secretAccessor` per
   secret and `roles/datastore.user` project-wide (needed for Firestore
   checkpoints — see `firestore.rules`).
4. Builds the image via Cloud Build from the repo root using the project's
   `Dockerfile` and tags it `gcr.io/$PROJECT_ID/synapse-api:latest`.
5. Renders `cloud-run-service.yaml` (substitutes `PROJECT_ID` and rewrites the
   secret references to point at the per-key secrets created in step 2) and
   applies it via `gcloud run services replace`.
6. Adds the public `roles/run.invoker` binding so the API is reachable without
   auth (matches the open-access design).

## Firebase Hosting (frontend)

See `firebase.json` and `.firebaserc` at the repo root.

```bash
cd frontend && npm install && npm run build
cd ..
firebase deploy --only hosting
```

`firebase.json` rewrites `/api/**` to the Cloud Run service so the frontend can
call the API on the same origin.

## Firestore rules

```bash
firebase deploy --only firestore:rules,firestore:indexes
```

Rules are in `firestore.rules`. They deny all client-SDK access; backend access
is controlled by IAM on the runtime SA, which the Cloud Run deploy script
configures automatically.

## Neon pgvector setup

One-time, before the first ingestion run:

```bash
uv run python -m scripts.setup_pgvector
```

The runtime client (`embedding/qdrant_client.py`) also runs the same DDL on
first connection, so this step is verification rather than a hard requirement.
