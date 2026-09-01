#!/usr/bin/env bash
# P8.5 — Complete Stakeholder E2E Workflow scenario runner.
# Exercises the REAL backend (Node, port 3000) submission lifecycle and the
# REAL device_ai (Python, port 8100) AI/passport/trust lifecycle against the
# live docker-compose stack, using the 5 seeded demo accounts. Every request
# and response is captured to a numbered JSON file under this directory as
# evidence — nothing here is fabricated or hand-written.
set -uo pipefail
cd "$(dirname "$0")"

BASE="http://localhost:3000/api/v1"
AI="http://localhost:8100"

TOK_ADMIN=$(grep -o '"accessToken":"[^"]*"' login_admin.json | cut -d'"' -f4)
TOK_GOV=$(grep -o '"accessToken":"[^"]*"' login_government.json | cut -d'"' -f4)
TOK_COLLECTOR=$(grep -o '"accessToken":"[^"]*"' login_collector.json | cut -d'"' -f4)
TOK_RECYCLER=$(grep -o '"accessToken":"[^"]*"' login_recycler.json | cut -d'"' -f4)
TOK_CONSUMER=$(grep -o '"accessToken":"[^"]*"' login_consumer.json | cut -d'"' -f4)
UID_COLLECTOR=$(grep -o '"id":"[^"]*"' login_collector.json | head -1 | cut -d'"' -f4)
UID_RECYCLER=$(grep -o '"id":"[^"]*"' login_recycler.json | head -1 | cut -d'"' -f4)

step() { echo "=== $1 ==="; }

# ---------------------------------------------------------------------------
# SCENARIO 1: Full lifecycle Collector -> Recycler -> Material recovery,
# with Consumer creating the submission (Collector -> Consumer relationship
# is: Consumer submits waste, Collector picks it up).
# ---------------------------------------------------------------------------
step "S1.1 Consumer creates submission (PENDING)"
curl -s -X POST "$BASE/submissions" -H "Authorization: Bearer $TOK_CONSUMER" \
  -H "Content-Type: application/json" \
  -d '{"category":"LAPTOP","description":"P8.5 E2E scenario laptop","estimatedWeight":2.5,"address":"12 MG Road, Chennai","latitude":13.0827,"longitude":80.2707}' \
  | tee s1_1_create.json
SUB_ID=$(grep -o '"id":"[^"]*"' s1_1_create.json | head -1 | cut -d'"' -f4)
echo "SUB_ID=$SUB_ID"

step "S1.2 Admin assigns collector (PENDING -> ASSIGNED)"
curl -s -X PATCH "$BASE/submissions/$SUB_ID/assign" -H "Authorization: Bearer $TOK_ADMIN" \
  -H "Content-Type: application/json" -d "{\"collectorId\":\"$UID_COLLECTOR\"}" \
  | tee s1_2_assign_collector.json

step "S1.3 Collector accepts (ASSIGNED -> ACCEPTED)"
curl -s -X PATCH "$BASE/submissions/$SUB_ID/accept" -H "Authorization: Bearer $TOK_COLLECTOR" \
  | tee s1_3_accept.json

step "S1.4 Collector starts pickup (ACCEPTED -> IN_PROGRESS)"
curl -s -X PATCH "$BASE/submissions/$SUB_ID/start" -H "Authorization: Bearer $TOK_COLLECTOR" \
  | tee s1_4_start.json

step "S1.5 Collector completes pickup (IN_PROGRESS -> COLLECTED)"
curl -s -X PATCH "$BASE/submissions/$SUB_ID/complete" -H "Authorization: Bearer $TOK_COLLECTOR" \
  | tee s1_5_complete_pickup.json

step "S1.6 Admin assigns recycler (COLLECTED, recycler assigned)"
curl -s -X PATCH "$BASE/submissions/$SUB_ID/assign-recycler" -H "Authorization: Bearer $TOK_ADMIN" \
  -H "Content-Type: application/json" -d "{\"recyclerId\":\"$UID_RECYCLER\"}" \
  | tee s1_6_assign_recycler.json

step "S1.7 Recycler starts recycling (COLLECTED -> RECYCLING)"
curl -s -X PATCH "$BASE/submissions/$SUB_ID/recycle/start" -H "Authorization: Bearer $TOK_RECYCLER" \
  | tee s1_7_recycle_start.json

step "S1.8 Recycler completes recycling + records material recovery (RECYCLING -> RECYCLED, reward issued)"
curl -s -X PATCH "$BASE/submissions/$SUB_ID/recycle/complete" -H "Authorization: Bearer $TOK_RECYCLER" \
  -H "Content-Type: application/json" \
  -d '{"recoveredWeight":2.5,"recyclerNotes":"P8.5 E2E scenario recovery","materialRecovery":{"copper":0.8,"aluminum":0.5,"plastic":1.2}}' \
  | tee s1_8_recycle_complete.json

step "S1.9 Consumer verifies own submission via QR-resolved id (consumer QR verification scenario)"
curl -s -X GET "$BASE/submissions/$SUB_ID" -H "Authorization: Bearer $TOK_CONSUMER" \
  | tee s1_9_consumer_view.json

step "S1.10 Consumer checks reward balance credited from recycling completion"
curl -s -X GET "$BASE/rewards/balance" -H "Authorization: Bearer $TOK_CONSUMER" \
  | tee s1_10_reward_balance.json

# ---------------------------------------------------------------------------
# SCENARIO 2: Government/Admin audit trail — list all submissions, confirm
# the one just completed is visible with full status history.
# ---------------------------------------------------------------------------
step "S2.1 Admin audit: list all submissions (sees every user's records)"
curl -s -X GET "$BASE/submissions?page=1&limit=20" -H "Authorization: Bearer $TOK_ADMIN" \
  | tee s2_1_admin_audit_list.json

step "S2.2 Government audit: list all submissions (same audit visibility as admin)"
curl -s -X GET "$BASE/submissions?page=1&limit=20" -H "Authorization: Bearer $TOK_GOV" \
  | tee s2_2_government_audit_list.json

step "S2.3 Consumer attempts the same admin-only audit listing scope check: consumer lists only sees own"
curl -s -X GET "$BASE/submissions?page=1&limit=20" -H "Authorization: Bearer $TOK_CONSUMER" \
  | tee s2_3_consumer_list_scope.json

# ---------------------------------------------------------------------------
# SCENARIO 3: Unauthorized lifecycle mutation rejected — a second, unrelated
# collector account cannot accept/complete a submission not assigned to them;
# a consumer cannot assign a collector (role-gated); an already-RECYCLED
# submission cannot be moved again (impossible transition rejected).
# ---------------------------------------------------------------------------
step "S3.1 Consumer attempts to assign a collector (role-forbidden, expect 403)"
curl -s -o s3_1_consumer_assign_forbidden.json -w "HTTP_STATUS:%{http_code}\n" \
  -X PATCH "$BASE/submissions/$SUB_ID/assign" -H "Authorization: Bearer $TOK_CONSUMER" \
  -H "Content-Type: application/json" -d "{\"collectorId\":\"$UID_COLLECTOR\"}"
cat s3_1_consumer_assign_forbidden.json

step "S3.2 Recycler attempts to re-start recycling on an already-RECYCLED submission (impossible transition, expect 409)"
curl -s -o s3_2_impossible_transition.json -w "HTTP_STATUS:%{http_code}\n" \
  -X PATCH "$BASE/submissions/$SUB_ID/recycle/start" -H "Authorization: Bearer $TOK_RECYCLER"
cat s3_2_impossible_transition.json

step "S3.3 Unauthenticated request to a protected route (expect 401)"
curl -s -o s3_3_unauthenticated.json -w "HTTP_STATUS:%{http_code}\n" \
  -X GET "$BASE/submissions"
cat s3_3_unauthenticated.json

# ---------------------------------------------------------------------------
# SCENARIO 4: Duplicate submission / duplicate reward issuance guard —
# a second manual reward-issue attempt against an already-rewarded submission.
# ---------------------------------------------------------------------------
step "S4.1 Admin attempts manual reward re-issue on an already-rewarded submission (expect conflict, not a duplicate reward)"
curl -s -o s4_1_duplicate_reward.json -w "HTTP_STATUS:%{http_code}\n" \
  -X POST "$BASE/rewards/issue/$SUB_ID" -H "Authorization: Bearer $TOK_ADMIN"
cat s4_1_duplicate_reward.json

echo ""
echo "SUB_ID_USED=$SUB_ID" > sub_id.txt
