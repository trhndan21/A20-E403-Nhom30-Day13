# python scripts/validate_logs.py
import json
import sys
from pathlib import Path

LOG_PATH = Path("data/logs.jsonl")
REQUIRED_FIELDS = {"ts", "level", "service", "event", "correlation_id"}
ENRICHMENT_FIELDS = {"user_id_hash", "session_id", "feature", "model"}

def main() -> None:
    if not LOG_PATH.exists():
        print(f"Error: {LOG_PATH} not found. Run the app and send some requests first.")
        sys.exit(1)

    records = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not records:
        print("Error: No valid JSON logs found in data/logs.jsonl")
        sys.exit(1)

    total = len(records)
    missing_required = 0
    missing_enrichment = 0
    pii_hits = []
    correlation_ids = set()

    for rec in records:
        # Check required fields (global)
        if not {"ts", "level", "event"}.issubset(rec.keys()):
            missing_required += 1
            
        # Context-specific checks for API requests
        if rec.get("service") == "api":
            if "correlation_id" not in rec or rec.get("correlation_id") == "MISSING":
                missing_required += 1
            
            if not ENRICHMENT_FIELDS.issubset(rec.keys()):
                missing_enrichment += 1

        # Check PII (naive check for @ or common test credit card)
        raw = json.dumps(rec)
        if "@" in raw or "4111" in raw:
            pii_hits.append(rec.get("event", "unknown"))

        # Collect correlation IDs
        cid = rec.get("correlation_id")
        if cid and cid != "MISSING":
            correlation_ids.add(cid)

    print("--- Lab Verification Results ---")
    print(f"Total log records analyzed: {total}")
    print(f"Records with missing required fields: {missing_required}")
    print(f"Records with missing enrichment (context): {missing_enrichment}")
    print(f"Unique correlation IDs found: {len(correlation_ids)}")
    print(f"Potential PII leaks detected: {len(pii_hits)}")
    if pii_hits:
        print(f"  Events with leaks: {set(pii_hits)}")
    
    print("\n--- Grading Scorecard (Estimates) ---")
    score = 100
    if missing_required > 0:
        score -= 30
        print("- [FAILED] Missing required fields (ts, level, etc.)")
    else:
        print("+ [PASSED] Basic JSON schema")

    if len(correlation_ids) < 2:
        score -= 20
        print("- [FAILED] Correlation ID propagation (less than 2 unique IDs)")
    else:
        print("+ [PASSED] Correlation ID propagation")

    if missing_enrichment > 0:
        score -= 20
        print("- [FAILED] Log enrichment (missing user_id_hash, etc.)")
    else:
        print("+ [PASSED] Log enrichment")

    if pii_hits:
        score -= 30
        print("- [FAILED] PII scrubbing (found @ or test credit card)")
    else:
        print("+ [PASSED] PII scrubbing")

    print(f"\nEstimated Score: {max(0, score)}/100")

if __name__ == "__main__":
    main()
