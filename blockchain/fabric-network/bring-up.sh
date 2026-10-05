#!/usr/bin/env bash
#
# EcoTrace India — Hyperledger Fabric local dev/demo network bring-up (P10.2).
#
# Codifies the known-good, live-verified P9.2 / P9.6 / P9.7 bring-up
# sequence for the local single-machine Fabric network (2 orgs + orderer,
# CA-issued identities, channel "ecotrace-channel", the ecotrace-lifecycle
# chaincode deployed as Chaincode-as-a-Service) so it can be reproduced by
# another session without re-discovering the Windows/Docker-Desktop fixes
# by trial and error. See docs/engineering/09_BLOCKCHAIN.md for the full
# narrative and troubleshooting guide.
#
# This script does NOT:
#   - modify blockchain/chaincode/ecotrace-lifecycle's source or business logic
#   - modify intelligence/device_ai's FabricGatewayClient, FabricExternalTrustLedger,
#     passport, or any Device Intelligence business logic
#   - modify the root docker-compose.yml or start/stop ecotrace-backend,
#     ecotrace-device-ai, ecotrace-frontend, ecotrace-postgres, unless the
#     operator explicitly passes --with-device-ai
#   - rebuild the chaincode (no `tsc`, no touching `dist/`) — it installs the
#     already-existing, already-verified CCaaS package as-is
#   - run `network.sh down`, `docker system prune`, `docker volume prune`,
#     or `rm -rf organizations` — teardown is a separate, explicit, human
#     decision (see the doc's "Shutdown" section)
#   - create a device, a submission, or touch any consumer/collector/recycler
#     data — this script only proves the Fabric infrastructure itself
#
# Idempotent by design: every stage first asks "does this already exist /
# is this already done?" and only acts when the answer is no. Rerunning
# this script against an already-up network is expected to be a fast
# no-op that reprints the connection details.
#
# Usage:
#   ./blockchain/fabric-network/bring-up.sh                # infrastructure only
#   ./blockchain/fabric-network/bring-up.sh --with-device-ai  # also applies the
#                                           existing Fabric override to the
#                                           running device-ai container and
#                                           verifies GET /system/blockchain/health
#
set -uo pipefail
# Deliberately NOT `set -e`: many stages check a command's exit code to
# decide "already done" vs "needs doing" (e.g. `peer channel list` failing
# just means "not joined yet") and must not abort the whole script on a
# merely-informative nonzero exit.

# ---------------------------------------------------------------------------
# Paths (all relative to this script's own location, not the caller's cwd)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_DIR="$SCRIPT_DIR/bootstrap"
TEST_NETWORK_DIR="$BOOTSTRAP_DIR/fabric-samples/test-network"
CHAINCODE_DIR="$SCRIPT_DIR/../chaincode/ecotrace-lifecycle"
CCAAS_PACKAGE_DIR="$BOOTSTRAP_DIR/ccaas-package"
CCAAS_PACKAGE_TAR="$CCAAS_PACKAGE_DIR/ecotrace-lifecycle-ccaas.tar.gz"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OVERRIDE_FILE="$BOOTSTRAP_DIR/docker-compose.p96-fabric-override.yml"

CHANNEL_NAME="ecotrace-channel"
CC_NAME="ecotrace-lifecycle"
CC_VERSION="1.0"
CC_SEQUENCE="1"
CCAAS_ADDRESS="0.0.0.0:9999"
CCAAS_LOG="$BOOTSTRAP_DIR/ccaas_server_current.log"
CCAAS_PIDFILE="$BOOTSTRAP_DIR/ccaas_server_current.pid"

WITH_DEVICE_AI="false"
for arg in "$@"; do
  case "$arg" in
    --with-device-ai) WITH_DEVICE_AI="true" ;;
    -h|--help)
      echo "Usage: $0 [--with-device-ai]"
      echo "  --with-device-ai  Also apply the existing Fabric override to the"
      echo "                    running device-ai container and verify"
      echo "                    GET /system/blockchain/health reports 'connected'."
      exit 0
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Minimal logging (kept local to this script — not borrowed from
# fabric-samples' scripts/utils.sh, so this script has no fragile
# dependency on that vendored tree's internal file layout).
# ---------------------------------------------------------------------------
C_GREEN=$'\033[0;32m'; C_YELLOW=$'\033[0;33m'; C_RED=$'\033[0;31m'; C_RESET=$'\033[0m'
info()  { echo "${C_GREEN}[bring-up]${C_RESET} $*"; }
warn()  { echo "${C_YELLOW}[bring-up]${C_RESET} $*"; }
fail()  { echo "${C_RED}[bring-up] ERROR:${C_RESET} $*" >&2; exit 1; }
skip()  { echo "${C_GREEN}[bring-up]${C_RESET} $* — already satisfied, skipping."; }

wait_for_tcp() {
  # wait_for_tcp <host> <port> <label> [max_seconds]
  local host="$1" port="$2" label="$3" max="${4:-60}" waited=0
  until (exec 3<>"/dev/tcp/$host/$port") 2>/dev/null; do
    exec 3>&- 2>/dev/null || true
    waited=$((waited + 2))
    if [ "$waited" -ge "$max" ]; then
      fail "$label did not become reachable at $host:$port within ${max}s."
    fi
    sleep 2
  done
  exec 3>&- 2>/dev/null || true
  info "$label is reachable at $host:$port."
}

container_state() {
  # Prints "running", "exited", or "absent" for a container name.
  local name="$1"
  local state
  state="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || true)"
  if [ -z "$state" ]; then
    echo "absent"
  elif [ "$state" = "running" ]; then
    echo "running"
  else
    echo "exited"
  fi
}

# ===========================================================================
# Stage 1 — Docker availability
# ===========================================================================
stage_check_docker() {
  info "Stage 1/13: checking Docker availability."
  command -v docker >/dev/null 2>&1 || fail "docker CLI not found on PATH."
  docker info >/dev/null 2>&1 || fail "Docker daemon is not reachable (is Docker Desktop running?)."
  if docker compose version >/dev/null 2>&1; then
    info "docker compose (v2 plugin) available."
  else
    fail "docker compose (v2 plugin) not available — required by fabric-samples' compose files."
  fi
}

# ===========================================================================
# Stage 2 — Required binaries / artifacts exist (never auto-downloads)
# ===========================================================================
stage_check_prereqs() {
  info "Stage 2/13: checking required Fabric binaries and artifacts."
  [ -d "$TEST_NETWORK_DIR" ] || fail \
    "fabric-samples/test-network not found under $BOOTSTRAP_DIR. Run
    'blockchain/fabric-network/bootstrap/bootstrap.sh' first (one-time,
    downloads ~350MB of Fabric binaries/images and clones fabric-samples —
    this script deliberately does not do that automatically)."

  local bindir="$BOOTSTRAP_DIR/fabric-samples/bin"
  for bin in peer orderer configtxgen fabric-ca-client osnadmin; do
    if [ -x "$bindir/$bin" ] || [ -x "$bindir/$bin.exe" ] || command -v "$bin" >/dev/null 2>&1; then
      :
    else
      fail "Required Fabric binary '$bin' not found under $bindir (and not on PATH). Re-run bootstrap.sh."
    fi
  done
  export PATH="$bindir:$PATH"

  [ -f "$CHAINCODE_DIR/dist/index.js" ] || fail \
    "$CHAINCODE_DIR/dist/index.js not found — the chaincode has never been
    built. This script does not build chaincode; run 'npm run build' inside
    blockchain/chaincode/ecotrace-lifecycle/ once, out of band, if this is a
    genuinely fresh checkout."

  if [ ! -f "$CCAAS_PACKAGE_TAR" ]; then
    warn "Existing CCaaS package not found at $CCAAS_PACKAGE_TAR — repackaging"
    warn "the connection descriptor (metadata.json + connection.json) into a"
    warn "fresh tarball. This repackages the CCaaS descriptor only — it does"
    warn "NOT recompile or modify the chaincode source or dist/ output."
    mkdir -p "$CCAAS_PACKAGE_DIR"
    cat > "$CCAAS_PACKAGE_DIR/connection.json" <<EOF
{"address": "host.docker.internal:9999", "dial_timeout": "10s", "tls_required": false}
EOF
    cat > "$CCAAS_PACKAGE_DIR/metadata.json" <<EOF
{"type":"ccaas","label":"${CC_NAME}_${CC_VERSION}"}
EOF
    ( cd "$CCAAS_PACKAGE_DIR" && tar -czf code.tar.gz connection.json && tar -czf ecotrace-lifecycle-ccaas.tar.gz code.tar.gz metadata.json )
  fi
  info "CCaaS package present: $CCAAS_PACKAGE_TAR"
}

# ===========================================================================
# Stage 3 — Windows/Git-Bash MSYS path-conversion fix (P9.2 finding #1)
# ===========================================================================
stage_set_msys_env() {
  info "Stage 3/13: applying the Windows/Git-Bash path-conversion fix."
  case "$(uname -s 2>/dev/null || echo unknown)" in
    MINGW*|MSYS*)
      unset MSYS_NO_PATHCONV
      export MSYS2_ARG_CONV_EXCL="/etc/hyperledger;/var/hyperledger"
      info "Detected Git-Bash/MSYS — unset MSYS_NO_PATHCONV, scoped MSYS2_ARG_CONV_EXCL."
      ;;
    *)
      info "Not Git-Bash/MSYS — no path-conversion fix needed on this shell."
      ;;
  esac
}

# ===========================================================================
# Stage 4 — Working directories exist / correct
# ===========================================================================
stage_verify_dirs() {
  info "Stage 4/13: verifying working directories."
  [ -d "$TEST_NETWORK_DIR/compose" ] || fail "Missing $TEST_NETWORK_DIR/compose — corrupted fabric-samples checkout."
  [ -d "$TEST_NETWORK_DIR/organizations" ] || fail "Missing $TEST_NETWORK_DIR/organizations — corrupted fabric-samples checkout."
  mkdir -p "$TEST_NETWORK_DIR/channel-artifacts"

  # network.sh itself exports this (derived from DOCKER_HOST, stripped of a
  # leading "unix://") before every compose invocation against the test-net
  # files — without it, `docker compose ... up -d` fails outright with
  # "invalid spec: :/host/var/run/docker.sock: empty section between
  # colons" (confirmed by direct `docker compose config` validation while
  # writing this script). The peer container's docker.sock bind-mount is
  # for the classic Docker-in-Docker chaincode-build path this project does
  # NOT use (CCaaS instead, per P9.2 finding #3) — it only needs to be a
  # syntactically valid path, not a working socket, for compose to parse.
  local sock="${DOCKER_HOST:-/var/run/docker.sock}"
  export DOCKER_SOCK="${sock##unix://}"
  info "Working directories OK. Test-network root: $TEST_NETWORK_DIR"
}

# ===========================================================================
# Stage 5/6 — CA services + identity generation/enrollment (P9.2's
# "Certificate Authorities" crypto mode, reusing fabric-samples' own
# organizations/fabric-ca/registerEnroll.sh — never reinvented).
# Skipped entirely (non-destructive) if crypto material already exists:
# network.sh's own createOrgs() DELETES organizations/peerOrganizations
# unconditionally if present, so this script must never call that path
# when material already exists.
# ===========================================================================
stage_bring_up_cas_and_identities() {
  info "Stage 5-6/13: Fabric CA services + identity enrollment."
  cd "$TEST_NETWORK_DIR"

  if [ -d organizations/peerOrganizations/org1.example.com ] && \
     [ -d organizations/peerOrganizations/org2.example.com ] && \
     [ -d organizations/ordererOrganizations/example.com ]; then
    skip "Org/orderer crypto material already exists under organizations/"
    return 0
  fi

  warn "No existing crypto material found — bringing up CA servers and enrolling fresh identities."
  info "Starting ca_org1, ca_org2, ca_orderer (docker compose, single command — CAs did not"
  info "race during P9.2; only orderer+peers needed sequential starts)."
  docker compose -f compose/compose-ca.yaml up -d

  wait_for_tcp localhost 7054 "ca_org1" 60
  wait_for_tcp localhost 8054 "ca_org2" 60
  wait_for_tcp localhost 9054 "ca_orderer" 60

  # Reuse fabric-samples' own enrollment functions verbatim — this is the
  # exact code path network.sh's createOrgs() calls in "Certificate
  # Authorities" mode; we call it directly instead of going through
  # network.sh so we can skip it entirely when material already exists.
  . organizations/fabric-ca/registerEnroll.sh
  info "Enrolling Org1 identities..."
  createOrg1
  info "Enrolling Org2 identities..."
  createOrg2
  info "Enrolling Orderer Org identities..."
  createOrderer

  info "Generating connection profiles (ccp-generate.sh)."
  ./organizations/ccp-generate.sh
}

# ===========================================================================
# Stage 7 — genesis/channel artifact generation (reused if present)
# ===========================================================================
stage_generate_channel_artifacts() {
  info "Stage 7/13: channel genesis block."
  cd "$TEST_NETWORK_DIR"
  local block="channel-artifacts/${CHANNEL_NAME}.block"
  if [ -s "$block" ]; then
    skip "Genesis block already exists at $block"
    return 0
  fi
  export FABRIC_CFG_PATH="$TEST_NETWORK_DIR/configtx"
  info "Generating $block via configtxgen (profile ChannelUsingRaft)."
  configtxgen -profile ChannelUsingRaft -outputBlock "$block" -channelID "$CHANNEL_NAME" \
    || fail "configtxgen failed to generate the channel genesis block."
}

# ===========================================================================
# Stages 9-14 — orderer, peer0.org1, peer0.org2: started ONE AT A TIME
# (P9.2 finding #2: starting all three together races on Windows Docker
# Desktop — "mkdir C:\Program Files\Git\var: Access is denied"). Existing
# containers are reused (started if stopped, left alone if running) rather
# than recreated.
# ===========================================================================
COMPOSE_TEST_NET=(-f compose/compose-test-net.yaml -f "compose/docker/docker-compose-test-net.yaml")

start_or_reuse_service() {
  # start_or_reuse_service <container_name> <compose_service_name> <probe_port> <label>
  local container="$1" service="$2" port="$3" label="$4"
  cd "$TEST_NETWORK_DIR"
  case "$(container_state "$container")" in
    running)
      skip "$label container '$container' is already running"
      ;;
    exited)
      info "$label container '$container' exists but is stopped — starting it (reusing its volume, not recreating)."
      docker start "$container" >/dev/null || fail "Failed to start existing container $container."
      ;;
    absent)
      info "$label container '$container' does not exist — creating it via docker compose."
      docker compose "${COMPOSE_TEST_NET[@]}" up -d "$service" || fail "Failed to bring up $service."
      ;;
  esac
  wait_for_tcp localhost "$port" "$label" 60
}

stage_start_orderer() {
  info "Stage 9-10/13: orderer.example.com."
  start_or_reuse_service "orderer.example.com" "orderer.example.com" 7050 "orderer"
}

stage_start_peer_org1() {
  info "Stage 11-12/13: peer0.org1.example.com."
  start_or_reuse_service "peer0.org1.example.com" "peer0.org1.example.com" 7051 "peer0.org1"
}

stage_start_peer_org2() {
  info "Stage 13-14/13: peer0.org2.example.com."
  start_or_reuse_service "peer0.org2.example.com" "peer0.org2.example.com" 9051 "peer0.org2"
}

# ===========================================================================
# Stage 15/16 — create/join channel + anchor peers (idempotent: skipped
# entirely if peer0.org1 already lists the channel as joined). Mirrors
# fabric-samples' own scripts/createChannel.sh / scripts/orderer.sh /
# scripts/setAnchorPeer.sh logic exactly, just guarded so a rerun never
# retries a channel-join that would otherwise error out on "already exists".
# ===========================================================================
stage_create_and_join_channel() {
  info "Stage 15-16/13: channel create/join + anchor peers."
  cd "$TEST_NETWORK_DIR"
  export FABRIC_CFG_PATH="$TEST_NETWORK_DIR/../config"
  . scripts/envVar.sh   # setGlobals(), ORDERER_CA, PEER0_ORG1_CA, PEER0_ORG2_CA

  setGlobals 1
  if peer channel list 2>/dev/null | grep -qx "$CHANNEL_NAME"; then
    skip "peer0.org1 has already joined '$CHANNEL_NAME'"
    return 0
  fi

  warn "Channel not yet joined — creating/joining '$CHANNEL_NAME'."
  export ORDERER_ADMIN_TLS_SIGN_CERT="$TEST_NETWORK_DIR/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.crt"
  export ORDERER_ADMIN_TLS_PRIVATE_KEY="$TEST_NETWORK_DIR/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.key"
  local block="channel-artifacts/${CHANNEL_NAME}.block"

  local join_out
  join_out="$(osnadmin channel join --channelID "$CHANNEL_NAME" --config-block "$block" \
    -o localhost:7053 --ca-file "$ORDERER_CA" \
    --client-cert "$ORDERER_ADMIN_TLS_SIGN_CERT" --client-key "$ORDERER_ADMIN_TLS_PRIVATE_KEY" 2>&1)" || true
  if echo "$join_out" | grep -qi "already exists"; then
    info "Orderer already has channel '$CHANNEL_NAME' (idempotent join)."
  elif echo "$join_out" | grep -qi '"name": *"'"$CHANNEL_NAME"'"'; then
    info "Orderer joined channel '$CHANNEL_NAME'."
  else
    fail "osnadmin channel join failed: $join_out"
  fi

  for org in 1 2; do
    setGlobals "$org"
    local rc=1 tries=0
    while [ $rc -ne 0 ] && [ $tries -lt 5 ]; do
      sleep 2
      peer channel join -b "$block" >/tmp/bringup_join_org${org}.log 2>&1
      rc=$?
      tries=$((tries + 1))
    done
    if [ $rc -ne 0 ] && grep -qi "already exists\|already joined" /tmp/bringup_join_org${org}.log; then
      info "peer0.org$org already joined (idempotent)."
    elif [ $rc -ne 0 ]; then
      fail "peer0.org$org failed to join '$CHANNEL_NAME' after $tries attempts: $(cat /tmp/bringup_join_org${org}.log)"
    else
      info "peer0.org$org joined '$CHANNEL_NAME'."
    fi
  done

  info "Setting anchor peers for both orgs."
  for org in 1 2; do
    . scripts/setAnchorPeer.sh "$org" "$CHANNEL_NAME" || warn "setAnchorPeer for org$org reported a non-fatal issue (commonly: anchor already set)."
  done
}

# ===========================================================================
# Stage 17/18/19 — deploy the EXISTING ecotrace-lifecycle CCaaS package
# (never rebuilt), start the CCaaS server process if not already running,
# and verify the chaincode definition is committed on the channel.
# ===========================================================================
stage_deploy_chaincode() {
  info "Stage 17-19/13: ecotrace-lifecycle chaincode (CCaaS, reusing the existing package)."
  cd "$TEST_NETWORK_DIR"
  . scripts/envVar.sh

  # 19a. Is it already committed? If so, skip install/approve/commit entirely.
  setGlobals 1
  if peer lifecycle chaincode querycommitted --channelID "$CHANNEL_NAME" --name "$CC_NAME" >/tmp/bringup_committed.log 2>&1; then
    skip "Chaincode '$CC_NAME' is already committed on '$CHANNEL_NAME': $(cat /tmp/bringup_committed.log | tr '\n' ' ')"
  else
    warn "Chaincode not yet committed — installing/approving/committing the existing package."

    local package_id=""
    for org in 1 2; do
      setGlobals "$org"
      if ! peer lifecycle chaincode queryinstalled 2>/dev/null | grep -q "${CC_NAME}_${CC_VERSION}"; then
        info "Installing the existing CCaaS package on org$org."
        peer lifecycle chaincode install "$CCAAS_PACKAGE_TAR" || fail "Chaincode install failed for org$org."
      else
        info "Chaincode already installed on org$org."
      fi
    done

    setGlobals 1
    package_id="$(peer lifecycle chaincode queryinstalled 2>/dev/null | grep "${CC_NAME}_${CC_VERSION}" | sed -n 's/^Package ID: \(.*\), Label:.*/\1/p' | head -1)"
    [ -n "$package_id" ] || fail "Could not determine the installed chaincode Package ID."
    info "Package ID: $package_id"
    echo "$package_id" > "$BOOTSTRAP_DIR/ecotrace-lifecycle.package-id.txt"

    for org in 1 2; do
      setGlobals "$org"
      peer lifecycle chaincode approveformyorg \
        -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com --tls --cafile "$ORDERER_CA" \
        --channelID "$CHANNEL_NAME" --name "$CC_NAME" --version "$CC_VERSION" \
        --package-id "$package_id" --sequence "$CC_SEQUENCE" \
        || fail "approveformyorg failed for org$org."
    done

    setGlobals 1
    peer lifecycle chaincode commit \
      -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com --tls --cafile "$ORDERER_CA" \
      --channelID "$CHANNEL_NAME" --name "$CC_NAME" --version "$CC_VERSION" --sequence "$CC_SEQUENCE" \
      --peerAddresses localhost:7051 --tlsRootCertFiles "$PEER0_ORG1_CA" \
      --peerAddresses localhost:9051 --tlsRootCertFiles "$PEER0_ORG2_CA" \
      || fail "Chaincode commit failed."
    info "Chaincode '$CC_NAME' committed on '$CHANNEL_NAME'."
  fi

  # Resolve the package id even on the "already committed" path (needed to
  # start/verify the CCaaS server with the right CHAINCODE_ID below).
  if [ -f "$BOOTSTRAP_DIR/ecotrace-lifecycle.package-id.txt" ]; then
    PACKAGE_ID="$(cat "$BOOTSTRAP_DIR/ecotrace-lifecycle.package-id.txt")"
  else
    setGlobals 1
    PACKAGE_ID="$(peer lifecycle chaincode queryinstalled 2>/dev/null | grep "${CC_NAME}_${CC_VERSION}" | sed -n 's/^Package ID: \(.*\), Label:.*/\1/p' | head -1)"
    [ -n "$PACKAGE_ID" ] && echo "$PACKAGE_ID" > "$BOOTSTRAP_DIR/ecotrace-lifecycle.package-id.txt"
  fi
  [ -n "${PACKAGE_ID:-}" ] || fail "Could not resolve the chaincode Package ID needed for the CCaaS server."

  # 18. Start the CCaaS server (existing dist/, no rebuild) if not already listening.
  if (exec 3<>"/dev/tcp/localhost/9999") 2>/dev/null; then
    exec 3>&- 2>/dev/null || true
    skip "A CCaaS server is already listening on port 9999 (reusing it)."
  else
    info "Starting the ecotrace-lifecycle CCaaS server (existing dist/, no rebuild) on $CCAAS_ADDRESS."
    ( cd "$CHAINCODE_DIR" && \
      CHAINCODE_ID="$PACKAGE_ID" CHAINCODE_SERVER_ADDRESS="$CCAAS_ADDRESS" \
      nohup npx fabric-chaincode-node server \
        --chaincode-address="$CCAAS_ADDRESS" --chaincode-id="$PACKAGE_ID" \
        > "$CCAAS_LOG" 2>&1 & echo $! > "$CCAAS_PIDFILE" )
    wait_for_tcp localhost 9999 "CCaaS server" 30
    info "CCaaS server started (pid $(cat "$CCAAS_PIDFILE" 2>/dev/null), log: $CCAAS_LOG)."
  fi
}

# ===========================================================================
# Stage 20/21 — print connection details + activation env vars
# ===========================================================================
stage_print_connection_details() {
  echo
  info "=== Fabric connection details for device-ai ==="
  cat <<EOF
  Channel:                ecotrace-channel
  Chaincode:               ecotrace-lifecycle
  MSP ID:                  Org1MSP
  Peer (TLS SNI) endpoint: peer0.org1.example.com:7051
  Peer gRPC dial target:   host.docker.internal:7051   (from inside a container)
                           localhost:7051               (from the host)
  TLS root cert:           $TEST_NETWORK_DIR/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt
  Identity cert:           $TEST_NETWORK_DIR/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp/signcerts/cert.pem
  Identity key:            (the single *_sk file under)
                           $TEST_NETWORK_DIR/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp/keystore/
  CCaaS package ID:        ${PACKAGE_ID:-<see $BOOTSTRAP_DIR/ecotrace-lifecycle.package-id.txt>}
EOF
  echo
  info "=== Environment variables to activate Fabric on device-ai ==="
  cat <<'EOF'
  FABRIC_ENABLED=true
  EXTERNAL_TRUST_BACKEND=fabric
  FABRIC_CHANNEL_NAME=ecotrace-channel
  FABRIC_CHAINCODE_NAME=ecotrace-lifecycle
  FABRIC_MSP_ID=Org1MSP
  FABRIC_PEER_ENDPOINT=peer0.org1.example.com:7051
  FABRIC_GATEWAY_PEER_ENDPOINT=host.docker.internal:7051
  FABRIC_TLS_CERT_PATH=/fabric-creds/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt
  FABRIC_IDENTITY_CERT_PATH=/fabric-creds/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp/signcerts/cert.pem
  FABRIC_IDENTITY_KEY_PATH=/fabric-creds/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp/keystore/<the one *_sk file>
EOF
  echo
  info "These values are already encoded in the existing, reusable override file:"
  info "  $OVERRIDE_FILE"
  info "Apply it explicitly (never automatic) with:"
  info "  docker compose -f docker-compose.yml -f blockchain/fabric-network/bootstrap/docker-compose.p96-fabric-override.yml up -d device-ai"
  info "Restore the default (memory) provider with:"
  info "  docker compose -f docker-compose.yml up -d device-ai"
}

# ===========================================================================
# Optional: activate device-ai + verify GET /system/blockchain/health
# (only runs with --with-device-ai — never touches the demo stack by default)
# ===========================================================================
stage_activate_device_ai_and_verify() {
  [ "$WITH_DEVICE_AI" = "true" ] || { info "Skipping device-ai activation (pass --with-device-ai to enable). Infrastructure verification ends here."; return 0; }

  info "=== --with-device-ai: applying the Fabric override to the running device-ai container ==="
  [ -f "$OVERRIDE_FILE" ] || fail "Override file not found: $OVERRIDE_FILE"
  cd "$REPO_ROOT"
  docker compose -f docker-compose.yml -f "$OVERRIDE_FILE" up -d device-ai \
    || fail "Failed to recreate device-ai with the Fabric override."

  info "Waiting for device-ai health endpoint..."
  local tries=0
  until curl -fsS http://localhost:8100/health >/dev/null 2>&1; do
    tries=$((tries + 1))
    [ $tries -ge 30 ] && fail "device-ai did not become healthy after recreation."
    sleep 2
  done

  info "Checking GET /system/blockchain/health ..."
  local resp
  resp="$(curl -fsS http://localhost:8100/system/blockchain/health 2>&1)" || fail "Could not reach /system/blockchain/health: $resp"
  echo "$resp"
  if echo "$resp" | grep -q '"status":"connected"'; then
    info "VERIFIED: device-ai's FabricGatewayClient reports 'connected' against the real peer."
  else
    warn "device-ai's blockchain health did NOT report 'connected'. Not fabricating success — inspect the response above and docs/engineering/09_BLOCKCHAIN.md's troubleshooting section."
  fi
}

# ===========================================================================
# Main
# ===========================================================================
main() {
  stage_check_docker
  stage_check_prereqs
  stage_set_msys_env
  stage_verify_dirs
  stage_bring_up_cas_and_identities
  stage_generate_channel_artifacts
  stage_start_orderer
  stage_start_peer_org1
  stage_start_peer_org2
  stage_create_and_join_channel
  stage_deploy_chaincode
  stage_print_connection_details
  stage_activate_device_ai_and_verify
  echo
  info "Fabric infrastructure bring-up complete. No device was created, no submission"
  info "was touched, no consumer/collector/recycler data was modified — this script"
  info "verifies infrastructure only, per the task's explicit scope."
}

main "$@"
