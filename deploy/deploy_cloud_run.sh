#!/usr/bin/env bash
# Deploy SYNAPSE backend to Cloud Run.
#
# What this does (idempotent — safe to re-run):
#   1. Validates PROJECT_ID and REGION are set (or sourced from .env / gcloud).
#   2. Enables the GCP APIs required for Cloud Run, Artifact Registry,
#      Secret Manager, and Firestore.
#   3. Creates/updates the `synapse-secrets` Secret Manager secret from .env,
#      adding a new version on every run so you can roll back.
#   4. Grants the Cloud Run runtime SA read access to the secret and
#      `roles/datastore.user` on Firestore.
#   5. Builds the container image with `gcloud builds submit` and tags it
#      `gcr.io/$PROJECT_ID/synapse-api:latest`.
#   6. Substitutes PROJECT_ID in cloud-run-service.yaml and deploys it via
#      `gcloud run services replace`.
#
# Usage:
#   PROJECT_ID=my-gcp-project REGION=us-central1 ./deploy/deploy_cloud_run.sh
#
# Prereqs: gcloud CLI authenticated (`gcloud auth login`), Docker not required
# (Cloud Build does the build remotely).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
SECRET_NAME="${SECRET_NAME:-synapse-secrets}"
SERVICE_NAME="${SERVICE_NAME:-synapse-api}"
IMAGE_NAME="${IMAGE_NAME:-synapse-api}"
REGION="${REGION:-us-central1}"

# Secret keys to copy from .env into Secret Manager. Must match the
# secretKeyRef.key entries in cloud-run-service.yaml.
SECRET_KEYS=(
  NEO4J_URI
  NEO4J_USERNAME
  NEO4J_PASSWORD
  GROQ_API_KEYS
  POSTGRES_URL
  GOOGLE_CLOUD_PROJECT
)

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
log()  { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command '$1' not found in PATH."
}

require_cmd gcloud
require_cmd sed

# Resolve PROJECT_ID
if [[ -z "${PROJECT_ID:-}" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
[[ -n "${PROJECT_ID:-}" ]] || fail "PROJECT_ID is not set. Export PROJECT_ID or run: gcloud config set project YOUR_PROJECT"

log "Project:  $PROJECT_ID"
log "Region:   $REGION"
log "Service:  $SERVICE_NAME"
log "Secret:   $SECRET_NAME"

# ----------------------------------------------------------------------------
# 1. Enable required APIs (idempotent)
# ----------------------------------------------------------------------------
log "Enabling required APIs ..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  containerregistry.googleapis.com \
  secretmanager.googleapis.com \
  firestore.googleapis.com \
  --project "$PROJECT_ID" >/dev/null

# ----------------------------------------------------------------------------
# 2. Build secret payload from .env
# ----------------------------------------------------------------------------
[[ -f "$ENV_FILE" ]] || fail ".env file not found at $ENV_FILE — copy .env.example first."

# We push each key as its own Secret Manager secret. The Cloud Run YAML
# references them with secretKeyRef.name == synapse-<key> would make N secrets;
# instead we use ONE secret per key under the same `synapse-secrets` family by
# encoding the key name into the secret name. Cloud Run YAML expects one
# secret per env var via secretKeyRef.{name,key}. Simplest approach: one
# secret named `synapse-secrets-${KEY}` per key, with `latest` version.

upsert_secret() {
  local secret_id="$1"
  local payload="$2"
  if gcloud secrets describe "$secret_id" --project "$PROJECT_ID" >/dev/null 2>&1; then
    log "  · Updating $secret_id (new version)"
    printf '%s' "$payload" | gcloud secrets versions add "$secret_id" \
      --project "$PROJECT_ID" --data-file=- >/dev/null
  else
    log "  · Creating $secret_id"
    printf '%s' "$payload" | gcloud secrets create "$secret_id" \
      --project "$PROJECT_ID" \
      --replication-policy=automatic \
      --data-file=- >/dev/null
  fi
}

# Read .env into associative array.
#
# Limitations of this minimal parser (matches dotenv conventions):
#   - Only `# comment` lines and blank lines are skipped.
#   - Inline comments (KEY=value # foo) become part of the value — keep
#     comments on their own lines in .env.
#   - Surrounding single/double quotes around the value are stripped.
declare -A ENV_VARS
while IFS='=' read -r key value; do
  # Skip comments and blank lines
  [[ -z "$key" || "$key" =~ ^# ]] && continue
  # Strip surrounding quotes
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  ENV_VARS["$key"]="$value"
done < <(grep -v '^\s*$' "$ENV_FILE" | grep -v '^\s*#')

log "Pushing secrets to Secret Manager ..."
for key in "${SECRET_KEYS[@]}"; do
  val="${ENV_VARS[$key]:-}"
  if [[ -z "$val" ]]; then
    warn "  · $key not set in $ENV_FILE — skipping"
    continue
  fi
  upsert_secret "${SECRET_NAME}-${key}" "$val"
done

# ----------------------------------------------------------------------------
# 3. Grant Cloud Run runtime SA access to secrets + Firestore
# ----------------------------------------------------------------------------
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SA="${RUNTIME_SA:-${PROJECT_NUMBER}-compute@developer.gserviceaccount.com}"

log "Granting IAM to runtime SA: $RUNTIME_SA"
for key in "${SECRET_KEYS[@]}"; do
  [[ -n "${ENV_VARS[$key]:-}" ]] || continue
  gcloud secrets add-iam-policy-binding "${SECRET_NAME}-${key}" \
    --project "$PROJECT_ID" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None >/dev/null
done

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/datastore.user" \
  --condition=None >/dev/null

# ----------------------------------------------------------------------------
# 4. Build & push image via Cloud Build
# ----------------------------------------------------------------------------
IMAGE_URI="gcr.io/${PROJECT_ID}/${IMAGE_NAME}:latest"
log "Submitting Cloud Build → $IMAGE_URI"
gcloud builds submit "$ROOT_DIR" \
  --project "$PROJECT_ID" \
  --tag "$IMAGE_URI" \
  --quiet

# ----------------------------------------------------------------------------
# 5. Render YAML and deploy
# ----------------------------------------------------------------------------
# Compute CORS_ORIGINS for the deployed service. Precedence:
#   1. Explicit CORS_ORIGINS env var (export before invoking the script)
#   2. CORS_ORIGINS from .env (read above into ENV_VARS)
#   3. Default: https://${PROJECT_ID}.web.app (Firebase Hosting URL) + localhost
DEPLOYED_CORS_ORIGINS="${CORS_ORIGINS:-${ENV_VARS[CORS_ORIGINS]:-}}"
if [[ -z "$DEPLOYED_CORS_ORIGINS" ]]; then
  DEPLOYED_CORS_ORIGINS="https://${PROJECT_ID}.web.app,http://localhost:5173"
  log "CORS_ORIGINS not provided — defaulting to $DEPLOYED_CORS_ORIGINS"
fi

RENDERED="$(mktemp)"
trap 'rm -f "$RENDERED"' EXIT

# The YAML uses a single PROJECT_ID placeholder for the image, and one
# `synapse-secrets` reference per env var. Patch both: PROJECT_ID and
# the secret name (synapse-secrets → synapse-secrets-<KEY>).
sed -e "s|gcr.io/PROJECT_ID/|gcr.io/${PROJECT_ID}/|g" \
    -e "s|CORS_ORIGINS_PLACEHOLDER|${DEPLOYED_CORS_ORIGINS}|g" \
    "$ROOT_DIR/cloud-run-service.yaml" > "$RENDERED"

# Rewrite each `name: synapse-secrets` paired with `key: <KEY>` into
# `name: synapse-secrets-<KEY>` + `key: latest`. We do this with a Python
# one-liner because sed can't easily do multiline yaml edits portably.
python3 - "$RENDERED" <<'PY'
import re, sys, pathlib
path = pathlib.Path(sys.argv[1])
text = path.read_text()
pattern = re.compile(
    r'(secretKeyRef:\s*\n\s*)name:\s*synapse-secrets\s*\n(\s*)key:\s*(\w+)',
    re.MULTILINE,
)
text = pattern.sub(
    lambda m: f"{m.group(1)}name: synapse-secrets-{m.group(3)}\n{m.group(2)}key: latest",
    text,
)
path.write_text(text)
PY

log "Deploying to Cloud Run ..."
gcloud run services replace "$RENDERED" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --quiet

# Make the service publicly reachable (matches the `no auth required` design).
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --member="allUsers" \
  --role="roles/run.invoker" >/dev/null

URL="$(gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" --region "$REGION" \
  --format='value(status.url)')"

log "Deployed: $URL"
log "Health:   $URL/api/v1/health"
