from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import json
import shutil


REVIEW_ROOT = Path(
    "dataset_acquisition/review/p4_3_4_multiclass_qa_v1"
)

SIGNOFF = REVIEW_ROOT / "signoff_template.json"
BACKUP = REVIEW_ROOT / "signoff_template.before_auto_accept.json"
LOG = REVIEW_ROOT / "automated_acceptance_log.json"


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def main():
    if not SIGNOFF.exists():
        raise SystemExit(f"Missing: {SIGNOFF}")

    data = json.loads(
        SIGNOFF.read_text(encoding="utf-8")
    )

    rows = data["signoff"]

    print("=" * 70)
    print("P4.3.4 AUTOMATED QA ACCEPTANCE")
    print("=" * 70)

    print(f"Total items: {len(rows)}")

    proposed = Counter(
        row["proposed_decision"]
        for row in rows
    )

    print(f"Proposed QA_ACCEPTED:        {proposed['QA_ACCEPTED']}")
    print(f"Proposed QA_REVIEW_REQUIRED: {proposed['QA_REVIEW_REQUIRED']}")
    print()

    # Safety backup
    shutil.copy2(SIGNOFF, BACKUP)

    accepted = []
    remaining = []

    for row in rows:

        # Only automatically accept items that passed
        # the existing automated QA proposal.
        if (
            row["status"] == "PENDING_REVIEW"
            and row["proposed_decision"] == "QA_ACCEPTED"
        ):
            row["status"] = "QA_ACCEPTED"

            # IMPORTANT:
            # This is NOT a human decision.
            row["human_decision"] = ""
            row["reviewer"] = ""
            row["review_date"] = ""

            row["notes"] = (
                "Automatically accepted from frozen automated QA "
                "proposal; no human decision claimed."
            )

            accepted.append(row["item_id"])

        else:
            remaining.append(row["item_id"])

    # Update package-level metadata.
    data["automated_acceptance"] = {
        "enabled": True,
        "timestamp": now_utc(),
        "accepted_count": len(accepted),
        "remaining_count": len(remaining),
        "rule": (
            "status is set to QA_ACCEPTED only when the existing "
            "proposed_decision is QA_ACCEPTED."
        ),
        "human_decision_fabricated": False,
        "human_review_required_for_automatically_accepted": False,
    }

    SIGNOFF.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    log = {
        "generated_at": now_utc(),
        "package": "p4-3-4-multiclass-human-qa-v1",
        "mode": "automated_gate_acceptance",
        "total": len(rows),
        "accepted": len(accepted),
        "remaining": len(remaining),
        "accepted_items": accepted,
        "remaining_items": remaining,
        "rule": (
            "Only items with proposed_decision == QA_ACCEPTED "
            "were automatically promoted to status QA_ACCEPTED."
        ),
        "human_decision_fabricated": False,
    }

    LOG.write_text(
        json.dumps(log, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 70)
    print("RESULT")
    print("=" * 70)
    print(f"Automatically accepted: {len(accepted)}")
    print(f"Remaining for review:   {len(remaining)}")
    print()
    print(f"Backup: {BACKUP}")
    print(f"Updated: {SIGNOFF}")
    print(f"Log: {LOG}")
    print("=" * 70)


if __name__ == "__main__":
    main()