#!/usr/bin/env python3
"""
Merge Election Data
Augments constituency_details.csv with party numbers and candidate ballot numbers
from Vote62 data.
"""

import csv
from datetime import datetime
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"


def load_csv(filename: str) -> list:
    """Load CSV file into list of dicts."""
    with open(filename, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_csv(rows: list, filename: str, fieldnames: list):
    """Save list of dicts to CSV."""
    with open(filename, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved: {filename} ({len(rows):,} rows)")


def normalize_name(name: str) -> str:
    """Normalize name for matching (remove spaces, common prefixes)."""
    if not name:
        return ""
    # Remove common Thai prefixes and normalize
    name = name.strip()
    return name


def main():
    print("=" * 60)
    print("Merging Election Data")
    print("=" * 60)

    # Load data files
    print("\nLoading data files...")

    constituency_details = load_csv(DATA_DIR / "constituency_details.csv")
    print(f"  ✓ constituency_details.csv: {len(constituency_details):,} rows")

    party_numbers = load_csv(DATA_DIR / "vote62_party_numbers.csv")
    print(f"  ✓ vote62_party_numbers.csv: {len(party_numbers):,} parties")

    vote62_candidates = load_csv(DATA_DIR / "vote62_candidates.csv")
    print(f"  ✓ vote62_candidates.csv: {len(vote62_candidates):,} candidates")

    # Build lookup tables
    print("\nBuilding lookup tables...")

    # Party name -> party ballot number
    party_number_lookup = {}
    for p in party_numbers:
        party_name = p.get("party_name", "").strip()
        party_no = p.get("party_no", "")
        if party_name and party_no:
            party_number_lookup[party_name] = party_no
    print(f"  ✓ Party number lookup: {len(party_number_lookup)} entries")

    # (province, cons_no, candidate_name) -> ballot number
    # Also (province, cons_no, party_name) -> ballot number for matching
    candidate_ballot_lookup = {}
    candidate_by_party_lookup = {}

    for c in vote62_candidates:
        province = c.get("province", "").strip()
        cons_no = c.get("cons_no", "").strip()
        candidate_name = c.get("candidate_name", "").strip()
        ballot_no = c.get("ballot_no", "")
        party = c.get("party", "").strip()

        # Primary key: province + cons_no + candidate_name
        key = (province, cons_no, candidate_name)
        candidate_ballot_lookup[key] = ballot_no

        # Secondary key: province + cons_no + party (for fallback matching)
        key2 = (province, cons_no, party)
        if key2 not in candidate_by_party_lookup:
            candidate_by_party_lookup[key2] = []
        candidate_by_party_lookup[key2].append(
            {"candidate_name": candidate_name, "ballot_no": ballot_no}
        )

    print(f"  ✓ Candidate ballot lookup: {len(candidate_ballot_lookup)} entries")

    # Process and augment constituency_details
    print("\nAugmenting data...")

    augmented_rows = []
    matched_party = 0
    matched_candidate = 0

    for row in constituency_details:
        new_row = row.copy()

        province = row.get("province", "").strip()
        cons_no = row.get("cons_no", "").strip()
        candidate_name = row.get("candidate_name", "").strip()
        party_name = row.get("party_name", "").strip()
        row_type = row.get("type", "")

        # Add party ballot number
        party_ballot_no = party_number_lookup.get(party_name, "")
        new_row["party_ballot_no"] = party_ballot_no
        if party_ballot_no:
            matched_party += 1

        # Add candidate ballot number (only for สส.แบ่งเขต)
        candidate_ballot_no = ""
        if row_type == "สส.แบ่งเขต" and candidate_name and candidate_name != "-":
            # Try exact match first
            key = (province, cons_no, candidate_name)
            candidate_ballot_no = candidate_ballot_lookup.get(key, "")

            # If not found, try fuzzy match by removing title prefixes
            if not candidate_ballot_no:
                # Try matching by party within same constituency
                key2 = (province, cons_no, party_name)
                candidates_in_cons = candidate_by_party_lookup.get(key2, [])

                for c in candidates_in_cons:
                    # Check if names are similar (one contains the other)
                    vote62_name = c["candidate_name"]
                    if (
                        candidate_name in vote62_name
                        or vote62_name in candidate_name
                        or candidate_name.split()[-1] in vote62_name
                    ):
                        candidate_ballot_no = c["ballot_no"]
                        break

            if candidate_ballot_no:
                matched_candidate += 1

        new_row["candidate_ballot_no"] = candidate_ballot_no

        augmented_rows.append(new_row)

    print(
        f"  ✓ Matched party numbers: {matched_party:,} / {len(constituency_details):,}"
    )
    print(f"  ✓ Matched candidate numbers: {matched_candidate:,}")

    # Define field order for output
    fieldnames = [
        "province",
        "prov_id",
        "cons_id",
        "cons_no",
        "zones",
        "registered_voters",
        "cons_turnout",
        "cons_turnout_pct",
        "cons_valid",
        "cons_invalid",
        "cons_blank",
        "party_list_turnout",
        "party_list_turnout_pct",
        "party_list_valid",
        "party_list_invalid",
        "party_list_blank",
        "type",
        "rank",
        "candidate_ballot_no",
        "candidate_name",
        "party_ballot_no",
        "party_name",
        "party_abbr",
        "votes",
        "vote_pct",
    ]

    # Save augmented data
    print("\nSaving augmented data...")
    save_csv(augmented_rows, DATA_DIR / "constituency_details_augmented.csv", fieldnames)

    # Print summary statistics
    print("\n" + "=" * 60)
    print("MERGE COMPLETE!")
    print("=" * 60)
    print(f"\nOutput: data/constituency_details_augmented.csv")
    print(f"  - Total rows: {len(augmented_rows):,}")
    print(f"  - Party numbers matched: {matched_party:,}")
    print(f"  - Candidate numbers matched: {matched_candidate:,}")

    # Show sample
    print("\n" + "=" * 60)
    print("SAMPLE OUTPUT (first constituency)")
    print("=" * 60)

    first_cons = []
    first_key = None
    for row in augmented_rows:
        key = (row["province"], row["cons_no"])
        if first_key is None:
            first_key = key
        if key == first_key:
            first_cons.append(row)
        elif first_key is not None:
            break

    print(f"\n{first_key[0]} เขต {first_key[1]}")
    print("-" * 80)

    # Show สส.แบ่งเขต
    print("\nสส.แบ่งเขต:")
    print(f"  {'เบอร์':<6} {'ชื่อผู้สมัคร':<35} {'เบอร์พรรค':<10} {'พรรค':<20} {'คะแนน':>10}")
    print(f"  {'-'*6} {'-'*35} {'-'*10} {'-'*20} {'-'*10}")

    for row in first_cons:
        if row["type"] == "สส.แบ่งเขต":
            cand_no = row["candidate_ballot_no"] or "-"
            party_no = row["party_ballot_no"] or "-"
            print(
                f"  {cand_no:<6} {row['candidate_name'][:33]:<35} {party_no:<10} {row['party_name'][:18]:<20} {int(float(row['votes'])):>10,}"
            )

    # Show บัญชีรายชื่อ (top 5)
    print("\nบัญชีรายชื่อ (top 5):")
    print(f"  {'เบอร์พรรค':<10} {'พรรค':<30} {'คะแนน':>15}")
    print(f"  {'-'*10} {'-'*30} {'-'*15}")

    count = 0
    for row in first_cons:
        if row["type"] == "บัญชีรายชื่อ" and count < 5:
            party_no = row["party_ballot_no"] or "-"
            print(
                f"  {party_no:<10} {row['party_name'][:28]:<30} {int(float(row['votes'])):>15,}"
            )
            count += 1


if __name__ == "__main__":
    main()
