from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_DECISIONS = {
    "A": "QA_ACCEPTED",
    "R": "QA_REVIEW_REQUIRED",
    "X": "QA_REJECTED",
}

REQUIRED_FIELDS = {
    "item_id",
    "class",
    "class_id",
    "canonical_image_filename",
    "source_image_filename",
    "sha256",
    "box_count",
    "issue_summary",
    "proposed_decision",
    "status",
    "human_decision",
    "reviewer",
    "review_date",
    "notes",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_atomic(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def open_image(path: Path):
    """
    Open the preview using the Windows default image viewer.
    """
    try:
        os.startfile(str(path))
    except AttributeError:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])


def validate_document(doc):
    if "signoff" not in doc:
        raise RuntimeError("signoff_template.json has no 'signoff' field")

    if not isinstance(doc["signoff"], list):
        raise RuntimeError("'signoff' must be a list")

    for i, row in enumerate(doc["signoff"]):
        missing = REQUIRED_FIELDS - set(row)
        if missing:
            raise RuntimeError(
                f"Row {i} ({row.get('item_id')}) missing fields: "
                f"{sorted(missing)}"
            )

        if row["status"] not in {
            "PENDING_REVIEW",
            "QA_ACCEPTED",
            "QA_REVIEW_REQUIRED",
            "QA_REJECTED",
        }:
            raise RuntimeError(
                f"Invalid status for {row['item_id']}: {row['status']}"
            )

        if row["human_decision"] not in {
            "",
            "QA_ACCEPTED",
            "QA_REVIEW_REQUIRED",
            "QA_REJECTED",
        }:
            raise RuntimeError(
                f"Invalid human_decision for {row['item_id']}: "
                f"{row['human_decision']}"
            )


def make_backup(path: Path):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(
        f"{path.stem}.backup_{timestamp}{path.suffix}"
    )
    shutil.copy2(path, backup)
    return backup


def class_counts(rows):
    result = {}
    for row in rows:
        cls = row["class"]
        result[cls] = result.get(cls, 0) + 1
    return dict(sorted(result.items()))


def print_summary(rows):
    pending = sum(r["status"] == "PENDING_REVIEW" for r in rows)
    accepted = sum(r["human_decision"] == "QA_ACCEPTED" for r in rows)
    review = sum(r["human_decision"] == "QA_REVIEW_REQUIRED" for r in rows)
    rejected = sum(r["human_decision"] == "QA_REJECTED" for r in rows)

    print()
    print("=" * 70)
    print("P4.3.4 HUMAN QA SUMMARY")
    print("=" * 70)
    print(f"Total:              {len(rows)}")
    print(f"Pending:            {pending}")
    print(f"QA_ACCEPTED:        {accepted}")
    print(f"QA_REVIEW_REQUIRED: {review}")
    print(f"QA_REJECTED:        {rejected}")
    print()
    print("By class:")
    for cls, count in class_counts(rows).items():
        done = sum(
            r["class"] == cls and r["human_decision"] != ""
            for r in rows
        )
        print(f"  {cls:12} {done}/{count}")
    print("=" * 70)
    print()


def get_reviewer():
    reviewer = input("Reviewer name/ID: ").strip()
    if not reviewer:
        raise RuntimeError("Reviewer name/ID cannot be empty")
    return reviewer


def choose_queue(rows, mode):
    pending = [
        r for r in rows
        if r["status"] == "PENDING_REVIEW"
    ]

    if mode == "flagged":
        pending = [
            r for r in pending
            if r["proposed_decision"] == "QA_REVIEW_REQUIRED"
        ]

    elif mode == "accepted":
        pending = [
            r for r in pending
            if r["proposed_decision"] == "QA_ACCEPTED"
        ]

    elif mode == "all":
        pass

    else:
        raise RuntimeError(f"Unknown queue mode: {mode}")

    return sorted(
        pending,
        key=lambda r: (str(r["class"]), str(r["item_id"])),
    )


def find_preview(review_root: Path, row):
    cls = row["class"]
    filename = row["canonical_image_filename"]

    direct = review_root / cls / "previews" / filename

    if direct.exists():
        return direct

    # The preview filenames contain qaNN_<sha-prefix>.jpg, so use qa_id
    # extracted from item_id when necessary.
    try:
        qa_num = int(str(row["item_id"]).rsplit("_", 1)[-1])
    except ValueError:
        qa_num = None

    if qa_num is not None:
        prefix = f"qa{qa_num:02d}_"
        matches = sorted(
            (review_root / cls / "previews").glob(prefix + "*")
        )
        if len(matches) == 1:
            return matches[0]

    # Last-resort filename search.
    matches = list(
        (review_root / cls / "previews").glob("*" + Path(filename).stem + "*")
    )

    if len(matches) == 1:
        return matches[0]

    return None


def review_row(
    review_root: Path,
    row,
    reviewer: str,
    log_path: Path,
):
    preview = find_preview(review_root, row)

    print()
    print("=" * 80)
    print(f"ITEM:                {row['item_id']}")
    print(f"CLASS:               {row['class']}")
    print(f"CLASS ID:            {row['class_id']}")
    print(f"BOX COUNT:            {row['box_count']}")
    print(f"PROPOSED DECISION:   {row['proposed_decision']}")
    print(f"ISSUE SUMMARY:       {row['issue_summary']}")
    print(f"CANONICAL IMAGE:     {row['canonical_image_filename']}")
    print(f"SHA256:              {row['sha256']}")
    print("=" * 80)

    if preview:
        print(f"Preview: {preview}")
        open_image(preview)
    else:
        print("WARNING: Preview not found.")

    print()
    print("[A] QA_ACCEPTED")
    print("[R] QA_REVIEW_REQUIRED")
    print("[X] QA_REJECTED")
    print("[S] Skip")
    print("[Q] Quit")
    print()

    while True:
        choice = input("Decision: ").strip().upper()

        if choice == "S":
            return "SKIP"

        if choice == "Q":
            return "QUIT"

        if choice in ALLOWED_DECISIONS:
            decision = ALLOWED_DECISIONS[choice]
            break

        print("Invalid choice. Use A, R, X, S or Q.")

    notes = input("Notes (optional): ").strip()

    previous_status = row["status"]
    previous_human = row["human_decision"]

    timestamp = now_utc()

    row["status"] = decision
    row["human_decision"] = decision
    row["reviewer"] = reviewer
    row["review_date"] = timestamp
    row["notes"] = notes

    event = {
        "timestamp": timestamp,
        "item_id": row["item_id"],
        "class": row["class"],
        "sha256": row["sha256"],
        "previous_status": previous_status,
        "previous_human_decision": previous_human,
        "human_decision": decision,
        "reviewer": reviewer,
        "notes": notes,
        "proposed_decision": row["proposed_decision"],
    }

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")

    return decision


def main():
    parser = argparse.ArgumentParser(
        description="P4.3.4 human QA reviewer"
    )

    parser.add_argument(
        "--review-root",
        type=Path,
        default=Path(
            "dataset_acquisition/review/"
            "p4_3_4_multiclass_qa_v1"
        ),
    )

    parser.add_argument(
        "--queue",
        choices=["flagged", "accepted", "all"],
        default="flagged",
        help=(
            "Review queue. 'flagged' reviews only "
            "QA_REVIEW_REQUIRED proposals."
        ),
    )

    parser.add_argument(
        "--reviewer",
        default=None,
        help="Reviewer name/ID. If omitted, prompt interactively.",
    )

    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a backup of signoff_template.json.",
    )

    args = parser.parse_args()

    review_root = args.review_root.resolve()
    signoff_path = review_root / "signoff_template.json"

    if not signoff_path.exists():
        raise SystemExit(
            f"ERROR: Missing {signoff_path}"
        )

    doc = load_json(signoff_path)
    validate_document(doc)

    rows = doc["signoff"]

    if args.reviewer:
        reviewer = args.reviewer.strip()
    else:
        reviewer = get_reviewer()

    if not reviewer:
        raise SystemExit("ERROR: Reviewer cannot be empty.")

    if not args.no_backup:
        backup = make_backup(signoff_path)
        print(f"Backup created: {backup}")

    log_path = review_root / "human_review_log.jsonl"

    queue = choose_queue(rows, args.queue)

    if not queue:
        print()
        print(f"No pending items in queue: {args.queue}")
        print_summary(rows)
        return 0

    print()
    print(f"Queue: {args.queue}")
    print(f"Items to review: {len(queue)}")
    print()

    processed = 0
    skipped = 0

    for index, row in enumerate(queue, start=1):
        print(f"\n[{index}/{len(queue)}]")

        result = review_row(
            review_root,
            row,
            reviewer,
            log_path,
        )

        if result == "QUIT":
            print("\nReview stopped by user.")
            break

        if result == "SKIP":
            skipped += 1
            continue

        processed += 1

        # Persist after EVERY decision.
        save_json_atomic(signoff_path, doc)

        print(f"Recorded: {result}")

    # Final validation.
    validate_document(doc)
    save_json_atomic(signoff_path, doc)

    print()
    print(f"Processed: {processed}")
    print(f"Skipped:   {skipped}")
    print_summary(rows)

    print(f"Updated: {signoff_path}")
    print(f"Audit:   {log_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())