#!/usr/bin/env bash
# EcoTrace India — environment-gated deploy entrypoint (P9.8).
#
# Every deploy goes through this script so there is exactly one place that
# decides what "deploying to <environment>" actually means — and, just as
# important, one place that refuses to pretend it can do something it
# genuinely cannot.
#
# Usage:
#   scripts/deployment/deploy.sh <environment>
#
# Environments:
#   local, demo   Real, working today: `docker compose up -d --build`
#                 against this repo's own docker-compose.yml. This is
#                 exactly what every P7-P9 phase report's live-verified
#                 stack has run.
#   staging       BLOCKED — ENVIRONMENT. No staging infrastructure,
#                 credentials, or target host exist anywhere in this
#                 project. Refuses loudly rather than deploying nowhere
#                 and reporting success.
#   production     BLOCKED — ENVIRONMENT, for the same reason, plus an
#                 explicit safety refusal: this script will never deploy
#                 to production even if such infrastructure is added later
#                 without a deliberate, separate, reviewed change to this
#                 gate — accidental production deploys are exactly what
#                 this script exists to prevent.

set -euo pipefail

ENVIRONMENT="${1:-}"

usage() {
  echo "Usage: $0 <local|demo|staging|production>" >&2
  exit 1
}

if [[ -z "$ENVIRONMENT" ]]; then
  usage
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

case "$ENVIRONMENT" in
  local|demo)
    echo "Deploying to '${ENVIRONMENT}' (docker compose, this host)..."
    ( cd "$REPO_ROOT" && docker compose up -d --build )
    echo "Deployed. Verify with: docker compose ps"
    ;;

  staging)
    echo "BLOCKED — ENVIRONMENT: no staging infrastructure exists." >&2
    echo "This project has never provisioned a staging host, DNS, TLS cert," >&2
    echo "or deployment credentials. Refusing rather than fabricating a" >&2
    echo "successful deploy to nowhere. See docs/engineering/11_DEPLOYMENT.md." >&2
    exit 2
    ;;

  production)
    echo "BLOCKED — ENVIRONMENT: no production infrastructure exists." >&2
    echo "This project has never provisioned production infrastructure or" >&2
    echo "credentials. This script will never deploy to production without a" >&2
    echo "deliberate, separately-reviewed change to this gate — accidental" >&2
    echo "production deploys are exactly what this refusal exists to prevent." >&2
    exit 2
    ;;

  *)
    echo "ERROR: unknown environment '${ENVIRONMENT}'." >&2
    usage
    ;;
esac
