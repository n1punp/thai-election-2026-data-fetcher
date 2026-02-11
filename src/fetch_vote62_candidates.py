#!/usr/bin/env python3
"""
Vote62 Candidate Fetcher
Fetches candidate names with their ballot numbers for each constituency
from https://www.vote62.com/69/candidates/สส.เขต/
"""

import json
import csv
import httpx
from datetime import datetime
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# Vote62 S3 data source
DATA_URL = "https://vote62-general-66-site.s3.ap-southeast-1.amazonaws.com/structure_f-69-1.json"


def fetch_vote62_data() -> dict:
    """Fetch candidate data from Vote62 S3 bucket."""
    print("Fetching Vote62 candidate data...")
    print("-" * 50)

    resp = httpx.get(DATA_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    print(f"  ✓ Provinces: {len(data.get('provinces', []))}")
    print(f"  ✓ Voting Districts: {len(data.get('votingDistricts', []))}")
    print(f"  ✓ Parties: {len(data.get('parties', []))}")
    print(f"  ✓ Candidates: {len(data.get('candidates', []))}")
    print(f"  ✓ Votables: {len(data.get('votables', []))}")

    return data


def build_constituency_lookup(data: dict) -> dict:
    """Build lookup from voting district code to province/constituency info."""
    lookup = {}

    for province in data.get("provinces", []):
        prov_name = province["name"]

        for district in province.get("districts", []):
            for subdistrict in district.get("subdistricts", []):
                for vd in subdistrict.get("votingDistricts", []):
                    code = vd["code"]
                    cons_no = vd["name"]

                    if code not in lookup:
                        lookup[code] = {
                            "province": prov_name,
                            "cons_no": cons_no,
                            "code": code,
                            "areas": []
                        }
                    lookup[code]["areas"].append(f"{district['name']}/{subdistrict['name']}")

    return lookup


def extract_constituency_candidates(data: dict) -> list:
    """Extract สส.เขต candidates with their ballot numbers."""

    cons_lookup = build_constituency_lookup(data)
    votables = data.get("votables", [])

    # Filter for สส.เขต only
    ss_khet = [v for v in votables if v.get("electionType") == "สส.เขต"]
    print(f"\nFound {len(ss_khet)} สส.เขต candidates")

    # Group by constituency
    by_constituency = {}
    for v in ss_khet:
        code = v.get("voteingDistrict", "")  # Note: typo in original data
        if code not in by_constituency:
            by_constituency[code] = []

        by_constituency[code].append({
            "ballot_no": v.get("no", ""),
            "candidate_name": v.get("candidate", ""),
            "party": v.get("party", "") if "party" in v else "",
            "resign": v.get("resign", "")
        })

    # Build result rows
    rows = []
    for code, candidates in sorted(by_constituency.items()):
        cons_info = cons_lookup.get(code, {})
        province = cons_info.get("province", code.split(".")[0] if "." in code else code)
        cons_no = cons_info.get("cons_no", code.split(".")[-1] if "." in code else "")

        # Sort candidates by ballot number
        candidates_sorted = sorted(candidates, key=lambda x: int(x["ballot_no"]) if x["ballot_no"].isdigit() else 999)

        for cand in candidates_sorted:
            rows.append({
                "province": province,
                "cons_no": cons_no,
                "cons_code": code,
                "ballot_no": cand["ballot_no"],
                "candidate_name": cand["candidate_name"],
                "party": cand.get("party", ""),
                "resign": cand.get("resign", "")
            })

    return rows


def get_party_from_candidates(data: dict) -> dict:
    """Build candidate to party mapping from candidates list."""
    candidates = data.get("candidates", [])
    return {c["name"]: c.get("party", "") for c in candidates}


def save_candidates_csv(rows: list, filename: str = "vote62_candidates.csv"):
    """Save candidates to CSV."""
    if not rows:
        print("No data to save")
        return

    with open(filename, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved: {filename} ({len(rows):,} rows)")


def save_candidates_by_constituency_csv(rows: list, filename: str = "vote62_by_constituency.csv"):
    """Save one row per constituency with all candidates in columns."""

    # Group by constituency
    by_cons = {}
    for row in rows:
        code = row["cons_code"]
        if code not in by_cons:
            by_cons[code] = {
                "province": row["province"],
                "cons_no": row["cons_no"],
                "cons_code": code,
                "candidates": []
            }
        by_cons[code]["candidates"].append(row)

    # Find max candidates per constituency
    max_candidates = max(len(c["candidates"]) for c in by_cons.values())

    # Build flat rows
    flat_rows = []
    for code, cons in sorted(by_cons.items()):
        flat = {
            "province": cons["province"],
            "cons_no": cons["cons_no"],
            "cons_code": code,
        }

        for i, cand in enumerate(cons["candidates"], 1):
            flat[f"no_{i}"] = cand["ballot_no"]
            flat[f"name_{i}"] = cand["candidate_name"]
            flat[f"party_{i}"] = cand["party"]

        flat_rows.append(flat)

    # Write CSV
    if flat_rows:
        # Build fieldnames
        fieldnames = ["province", "cons_no", "cons_code"]
        for i in range(1, max_candidates + 1):
            fieldnames.extend([f"no_{i}", f"name_{i}", f"party_{i}"])

        with open(filename, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(flat_rows)

        print(f"Saved: {filename} ({len(flat_rows):,} constituencies)")


def create_readable_report(rows: list, filename: str = "vote62_candidates_report.txt"):
    """Create human-readable report of candidates by constituency."""

    # Get party mapping
    party_map = {}
    for row in rows:
        if row["candidate_name"] and row["party"]:
            party_map[row["candidate_name"]] = row["party"]

    # Group by province then constituency
    by_province = {}
    for row in rows:
        prov = row["province"]
        cons = row["cons_no"]
        key = (prov, cons)

        if key not in by_province:
            by_province[key] = {
                "province": prov,
                "cons_no": cons,
                "cons_code": row["cons_code"],
                "candidates": []
            }
        by_province[key]["candidates"].append(row)

    lines = []
    lines.append("╔" + "═" * 98 + "╗")
    lines.append("║" + "รายชื่อผู้สมัคร สส.เขต ทุกเขตเลือกตั้ง".center(98) + "║")
    lines.append("║" + "Constituency MP Candidates by Ballot Number".center(98) + "║")
    lines.append("╠" + "═" * 98 + "╣")
    lines.append("║" + f"  แหล่งข้อมูล: https://www.vote62.com/69/candidates/สส.เขต/".ljust(98) + "║")
    lines.append("║" + f"  ดึงข้อมูลเมื่อ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".ljust(98) + "║")
    lines.append("║" + f"  จำนวนเขต: {len(by_province)} เขต | จำนวนผู้สมัคร: {len(rows)} คน".ljust(98) + "║")
    lines.append("╚" + "═" * 98 + "╝")

    current_province = None

    for key in sorted(by_province.keys()):
        cons_data = by_province[key]
        prov = cons_data["province"]
        cons_no = cons_data["cons_no"]
        candidates = cons_data["candidates"]

        # Province header
        if prov != current_province:
            current_province = prov
            lines.append("\n")
            lines.append("┏" + "━" * 98 + "┓")
            lines.append("┃" + f"  จังหวัด: {prov}".ljust(98) + "┃")
            lines.append("┗" + "━" * 98 + "┛")

        # Constituency
        lines.append("")
        lines.append(f"  ┌{'─' * 94}┐")
        lines.append(f"  │ เขต {cons_no} ({cons_data['cons_code']})".ljust(96) + "│")
        lines.append(f"  ├{'─' * 94}┤")
        lines.append(f"  │ {'เบอร์':<6} {'ชื่อผู้สมัคร':<45} {'พรรค':<40} │")
        lines.append(f"  ├{'─' * 94}┤")

        # Sort by ballot number
        sorted_cands = sorted(candidates, key=lambda x: int(x["ballot_no"]) if x["ballot_no"].isdigit() else 999)

        for cand in sorted_cands:
            no = cand["ballot_no"]
            name = cand["candidate_name"]
            party = cand.get("party", "") or party_map.get(name, "")

            # Truncate if needed
            name_display = name[:43] if len(name) > 43 else name
            party_display = party[:38] if len(party) > 38 else party

            resign = " (ลาออก)" if cand.get("resign") else ""
            lines.append(f"  │ {no:>4}   {name_display:<45} {party_display:<38}{resign} │")

        lines.append(f"  └{'─' * 94}┘")

    # Footer
    lines.append("\n")
    lines.append("╔" + "═" * 98 + "╗")
    lines.append("║" + " จบรายงาน (End of Report)".center(98) + "║")
    lines.append("╚" + "═" * 98 + "╝")

    report = "\n".join(lines)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Saved: {filename}")
    return report


def extract_party_ballot_numbers(data: dict) -> list:
    """Extract party ballot numbers (เบอร์พรรคการเมือง) from party list data."""

    votables = data.get("votables", [])

    # Filter for สส.บัญชีรายชื่อ (party list)
    party_list = [v for v in votables if v.get("electionType") == "สส.บัญชีรายชื่อ"]

    rows = []
    for p in party_list:
        rows.append({
            "party_no": p.get("no", ""),
            "party_name": p.get("party", ""),
            "resign": p.get("resign", "")
        })

    # Sort by party number
    rows.sort(key=lambda x: int(x["party_no"]) if x["party_no"].isdigit() else 999)

    return rows


def save_party_numbers_csv(rows: list, filename: str = "vote62_party_numbers.csv"):
    """Save party ballot numbers to CSV."""
    if not rows:
        print("No party data to save")
        return

    with open(filename, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["party_no", "party_name", "resign"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved: {filename} ({len(rows):,} parties)")


def main():
    print("=" * 50)
    print("Vote62 Candidate Fetcher")
    print("=" * 50)

    # Fetch data
    data = fetch_vote62_data()

    # Get party mapping from candidates list
    party_map = {c["name"]: c.get("party", "") for c in data.get("candidates", [])}

    # Extract candidates
    rows = extract_constituency_candidates(data)

    # Add party info from candidates list
    for row in rows:
        if not row.get("party") and row["candidate_name"] in party_map:
            row["party"] = party_map[row["candidate_name"]]

    print(f"\nProcessed {len(rows):,} candidate entries")

    # Extract party ballot numbers
    party_numbers = extract_party_ballot_numbers(data)
    print(f"Processed {len(party_numbers):,} party ballot numbers")

    # Save outputs
    print("\nSaving outputs...")
    save_candidates_csv(rows, DATA_DIR / "vote62_candidates.csv")
    save_candidates_by_constituency_csv(rows, DATA_DIR / "vote62_by_constituency.csv")
    save_party_numbers_csv(party_numbers, DATA_DIR / "vote62_party_numbers.csv")
    report = create_readable_report(rows, REPORTS_DIR / "vote62_candidates_report.txt")

    # Save raw JSON
    json_path = DATA_DIR / "vote62_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "fetched_at": datetime.now().isoformat(),
            "source": "https://www.vote62.com/69/candidates/สส.เขต/",
            "data_url": DATA_URL,
            "candidates": rows,
            "party_numbers": party_numbers,
            "raw_data": data
        }, f, ensure_ascii=False, indent=2)
    print(f"Saved: {json_path}")

    print("\n" + "=" * 50)
    print("FETCH COMPLETE!")
    print("=" * 50)
    print("\nOutput files:")
    print("  - data/vote62_candidates.csv          (all candidates, one per row)")
    print("  - data/vote62_by_constituency.csv     (one row per constituency)")
    print("  - data/vote62_party_numbers.csv       (party ballot numbers)")
    print("  - reports/vote62_candidates_report.txt (human-readable report)")
    print("  - data/vote62_data.json               (complete raw data)")

    # Print party numbers
    print("\n" + "=" * 50)
    print("เบอร์พรรคการเมือง (Party Ballot Numbers)")
    print("=" * 50)
    for p in party_numbers:
        resign = " (ลาออก)" if p.get("resign") else ""
        print(f"  เบอร์ {p['party_no']:>2}: {p['party_name']}{resign}")

    # Print sample candidates
    print("\n" + "=" * 50)
    print("SAMPLE: สส.เขต (first 3 constituencies)")
    print("=" * 50)

    # Group for display
    shown = set()
    for row in rows:
        key = (row["province"], row["cons_no"])
        if key not in shown and len(shown) < 3:
            shown.add(key)
            print(f"\n{row['province']} เขต {row['cons_no']}:")
            same_cons = [r for r in rows if r["province"] == row["province"] and r["cons_no"] == row["cons_no"]]
            for c in sorted(same_cons, key=lambda x: int(x["ballot_no"]) if x["ballot_no"].isdigit() else 999):
                print(f"  เบอร์ {c['ballot_no']:>2}: {c['candidate_name']:<35} ({c['party']})")


if __name__ == "__main__":
    main()
