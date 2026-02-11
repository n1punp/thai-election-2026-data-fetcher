#!/usr/bin/env python3
"""
Thailand Election Data Fetcher
Fetches election results from https://ectreport69.ect.go.th/
Includes detailed constituency-level data with candidates, party-list votes, and referendum results.
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

# API Endpoints
BASE_STATIC = "https://static-ectreport69.ect.go.th/data"
BASE_STATS = "https://stats-ectreport69.ect.go.th/data"

ENDPOINTS = {
    "provinces": f"{BASE_STATIC}/data/refs/info_province.json",
    "constituencies": f"{BASE_STATIC}/data/refs/info_constituency.json",
    "parties": f"{BASE_STATIC}/data/refs/info_party_overview.json",
    "mp_candidates": f"{BASE_STATIC}/data/refs/info_mp_candidate.json",
    "stats_cons": f"{BASE_STATS}/records/stats_cons.json",
    "stats_referendum": f"{BASE_STATS}/records/stats_referendum.json",
}


def fetch_data(url: str) -> dict | list | None:
    """Fetch JSON data from URL."""
    try:
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


def fetch_all_data() -> dict:
    """Fetch all election data from API endpoints."""
    print("Fetching Thailand Election Data...")
    print("-" * 50)

    data = {
        "fetched_at": datetime.now().isoformat(),
        "source": "https://ectreport69.ect.go.th",
    }

    for name, url in ENDPOINTS.items():
        print(f"  Fetching {name}...")
        result = fetch_data(url)
        if result:
            data[name] = result
            print(f"    ✓ Got {name}")
        else:
            print(f"    ✗ Failed {name}")

    return data


def create_constituency_details_csv(data: dict, filename: str = "constituency_details.csv"):
    """Create CSV with detailed constituency data including candidates and party-list."""

    # Build lookup tables
    parties_info = {int(p["id"]): p for p in data.get("parties", [])}
    mp_candidates = {c["mp_app_id"]: c for c in data.get("mp_candidates", [])}
    cons_info = {c["cons_id"]: c for c in data.get("constituencies", [])}
    prov_info = {p["prov_id"]: p for p in data.get("provinces", {}).get("province", [])}

    stats = data.get("stats_cons", {})
    rows = []

    for province in stats.get("result_province", []):
        prov_id = province["prov_id"]
        prov_name = prov_info.get(prov_id, {}).get("province", prov_id)

        for cons in province.get("constituencies", []):
            cons_id = cons["cons_id"]
            cons_data = cons_info.get(cons_id, {})
            cons_no = cons_data.get("cons_no", 0)
            zones = cons_data.get("zone", [])
            zone_str = ", ".join(zones) if zones else ""
            registered = cons_data.get("registered_vote", 0)

            if cons_no == 0:
                continue

            base_row = {
                "province": prov_name,
                "prov_id": prov_id,
                "cons_id": cons_id,
                "cons_no": cons_no,
                "zones": zone_str,
                "registered_voters": registered or 0,
                # Constituency MP (แบ่งเขต)
                "cons_turnout": cons.get("turn_out", 0),
                "cons_turnout_pct": cons.get("percent_turn_out", 0),
                "cons_valid": cons.get("valid_votes", 0),
                "cons_invalid": cons.get("invalid_votes", 0),
                "cons_blank": cons.get("blank_votes", 0),
                # Party-list (บัญชีรายชื่อ)
                "party_list_turnout": cons.get("party_list_turn_out", 0),
                "party_list_turnout_pct": cons.get("party_list_percent_turn_out", 0),
                "party_list_valid": cons.get("party_list_valid_votes", 0),
                "party_list_invalid": cons.get("party_list_invalid_votes", 0),
                "party_list_blank": cons.get("party_list_blank_votes", 0),
            }

            # Add candidate results (สส.แบ่งเขต)
            candidates = cons.get("candidates", [])
            sorted_candidates = sorted(candidates, key=lambda x: x.get("mp_app_vote", 0), reverse=True)

            for cand in sorted_candidates:
                mp_id = cand.get("mp_app_id", "")
                mp_info = mp_candidates.get(mp_id, {})
                party_id = cand.get("party_id", 0)
                party_info = parties_info.get(party_id, {})

                row = base_row.copy()
                row["type"] = "สส.แบ่งเขต"
                row["rank"] = cand.get("mp_app_rank", 0)
                row["candidate_name"] = mp_info.get("mp_app_name", mp_id)
                row["party_name"] = party_info.get("name", f"Party {party_id}")
                row["party_abbr"] = party_info.get("abbr", "")
                row["votes"] = cand.get("mp_app_vote", 0)
                row["vote_pct"] = cand.get("mp_app_vote_percent", 0)
                rows.append(row)

            # Add party-list results (บัญชีรายชื่อ)
            party_results = cons.get("result_party", [])
            sorted_parties = sorted(party_results, key=lambda x: x.get("party_list_vote", 0), reverse=True)

            for i, pr in enumerate(sorted_parties, 1):
                if pr.get("party_list_vote", 0) == 0:
                    continue

                party_id = pr.get("party_id", 0)
                party_info = parties_info.get(party_id, {})

                row = base_row.copy()
                row["type"] = "บัญชีรายชื่อ"
                row["rank"] = i
                row["candidate_name"] = "-"
                row["party_name"] = party_info.get("name", f"Party {party_id}")
                row["party_abbr"] = party_info.get("abbr", "")
                row["votes"] = pr.get("party_list_vote", 0)
                row["vote_pct"] = pr.get("party_list_vote_percent", 0)
                rows.append(row)

    if rows:
        fieldnames = [
            "province", "prov_id", "cons_id", "cons_no", "zones", "registered_voters",
            "cons_turnout", "cons_turnout_pct", "cons_valid", "cons_invalid", "cons_blank",
            "party_list_turnout", "party_list_turnout_pct", "party_list_valid", "party_list_invalid", "party_list_blank",
            "type", "rank", "candidate_name", "party_name", "party_abbr", "votes", "vote_pct"
        ]

        with open(filename, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"Saved: {filename} ({len(rows):,} rows)")

    return rows


def create_referendum_details_csv(data: dict, filename: str = "referendum_details.csv"):
    """Create CSV with referendum results per constituency."""

    cons_info = {c["cons_id"]: c for c in data.get("constituencies", [])}
    prov_info = {p["prov_id"]: p for p in data.get("provinces", {}).get("province", [])}

    ref_stats = data.get("stats_referendum", {})
    rows = []

    for province in ref_stats.get("result_province", []):
        prov_id = province["prov_id"]
        prov_name = prov_info.get(prov_id, {}).get("province", prov_id)

        for cons in province.get("constituencies", []):
            cons_id = cons["cons_id"]
            cons_data = cons_info.get(cons_id, {})
            cons_no = cons_data.get("cons_no", 0)
            zones = cons_data.get("zone", [])
            registered = cons_data.get("registered_vote", 0)

            if cons_no == 0:
                continue

            # Get referendum results
            ref_results = cons.get("referendum_results", {})
            for q_id, result in ref_results.items():
                row = {
                    "province": prov_name,
                    "prov_id": prov_id,
                    "cons_id": cons_id,
                    "cons_no": cons_no,
                    "zones": ", ".join(zones) if zones else "",
                    "registered_voters": registered or 0,
                    # Turnout
                    "ref_turnout": cons.get("referendum_turn_out", 0),
                    "ref_turnout_pct": round(cons.get("referendum_percent_turn_out", 0), 2),
                    # Valid/Invalid
                    "ref_valid": cons.get("referendum_valid_votes", 0),
                    "ref_valid_pct": round(cons.get("referendum_percent_valid_votes", 0), 2),
                    "ref_invalid": cons.get("referendum_invalid_votes", 0),
                    "ref_invalid_pct": round(cons.get("referendum_percent_invalid_votes", 0), 2),
                    # Results
                    "yes_votes": result.get("yes", 0),
                    "yes_pct": round(result.get("percent_yes", 0), 2),
                    "no_votes": result.get("no", 0),
                    "no_pct": round(result.get("percent_no", 0), 2),
                    "abstained": result.get("abstained", 0),
                    "abstained_pct": round(result.get("percent_abstained", 0), 2),
                    # Count progress
                    "counted_stations": cons.get("referendum_counted_vote_stations", 0),
                    "count_pct": round(cons.get("referendum_percent_count", 0), 2),
                }
                rows.append(row)

    if rows:
        with open(filename, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        print(f"Saved: {filename} ({len(rows):,} rows)")

    return rows


def create_constituency_summary_csv(data: dict, filename: str = "constituency_summary.csv"):
    """Create summary CSV with one row per constituency including referendum."""

    parties_info = {int(p["id"]): p for p in data.get("parties", [])}
    mp_candidates = {c["mp_app_id"]: c for c in data.get("mp_candidates", [])}
    cons_info = {c["cons_id"]: c for c in data.get("constituencies", [])}
    prov_info = {p["prov_id"]: p for p in data.get("provinces", {}).get("province", [])}

    # Build referendum lookup by cons_id
    ref_stats = data.get("stats_referendum", {})
    ref_by_cons = {}
    for province in ref_stats.get("result_province", []):
        for cons in province.get("constituencies", []):
            ref_by_cons[cons["cons_id"]] = cons

    stats = data.get("stats_cons", {})
    rows = []

    for province in stats.get("result_province", []):
        prov_id = province["prov_id"]
        prov_name = prov_info.get(prov_id, {}).get("province", prov_id)

        for cons in province.get("constituencies", []):
            cons_id = cons["cons_id"]
            cons_data = cons_info.get(cons_id, {})
            cons_no = cons_data.get("cons_no", 0)

            if cons_no == 0:
                continue

            zones = cons_data.get("zone", [])
            registered = cons_data.get("registered_vote", 0)

            # Get winner
            candidates = cons.get("candidates", [])
            winner = next((c for c in candidates if c.get("mp_app_rank") == 1), None)

            winner_name = ""
            winner_party = ""
            winner_votes = 0
            winner_pct = 0

            if winner:
                mp_id = winner.get("mp_app_id", "")
                mp_info = mp_candidates.get(mp_id, {})
                party_id = winner.get("party_id", 0)
                party_info = parties_info.get(party_id, {})

                winner_name = mp_info.get("mp_app_name", mp_id)
                winner_party = party_info.get("name", "")
                winner_votes = winner.get("mp_app_vote", 0)
                winner_pct = winner.get("mp_app_vote_percent", 0)

            # Get top party-list party
            party_results = cons.get("result_party", [])
            top_party_list = max(party_results, key=lambda x: x.get("party_list_vote", 0), default={})
            top_party_id = top_party_list.get("party_id", 0)
            top_party_info = parties_info.get(top_party_id, {})

            # Get referendum data
            ref_cons = ref_by_cons.get(cons_id, {})
            ref_results = ref_cons.get("referendum_results", {})
            ref_result = next(iter(ref_results.values()), {}) if ref_results else {}

            row = {
                "province": prov_name,
                "prov_id": prov_id,
                "cons_no": cons_no,
                "zones": ", ".join(zones) if zones else "",
                "registered_voters": registered or 0,
                # สส.แบ่งเขต stats
                "cons_turnout": cons.get("turn_out", 0),
                "cons_turnout_pct": round(cons.get("percent_turn_out", 0), 2),
                "cons_valid": cons.get("valid_votes", 0),
                "cons_invalid": cons.get("invalid_votes", 0),
                "cons_blank": cons.get("blank_votes", 0),
                # Winner info
                "winner_name": winner_name,
                "winner_party": winner_party,
                "winner_votes": winner_votes,
                "winner_pct": round(winner_pct, 2),
                # บัญชีรายชื่อ stats
                "party_list_turnout": cons.get("party_list_turn_out", 0),
                "party_list_turnout_pct": round(cons.get("party_list_percent_turn_out", 0), 2),
                "party_list_valid": cons.get("party_list_valid_votes", 0),
                "party_list_invalid": cons.get("party_list_invalid_votes", 0),
                "party_list_blank": cons.get("party_list_blank_votes", 0),
                "top_party_list_party": top_party_info.get("name", ""),
                "top_party_list_votes": top_party_list.get("party_list_vote", 0),
                "top_party_list_pct": round(top_party_list.get("party_list_vote_percent", 0), 2),
                # ประชามติ stats
                "ref_turnout": ref_cons.get("referendum_turn_out", 0),
                "ref_turnout_pct": round(ref_cons.get("referendum_percent_turn_out", 0), 2),
                "ref_valid": ref_cons.get("referendum_valid_votes", 0),
                "ref_invalid": ref_cons.get("referendum_invalid_votes", 0),
                "ref_yes": ref_result.get("yes", 0),
                "ref_yes_pct": round(ref_result.get("percent_yes", 0), 2),
                "ref_no": ref_result.get("no", 0),
                "ref_no_pct": round(ref_result.get("percent_no", 0), 2),
                "ref_abstained": ref_result.get("abstained", 0),
            }
            rows.append(row)

    if rows:
        with open(filename, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        print(f"Saved: {filename} ({len(rows):,} rows)")

    return rows


def create_readable_report(data: dict, filename: str = "election_report.txt"):
    """Create human-readable election report with all constituencies."""

    parties_info = {int(p["id"]): p for p in data.get("parties", [])}
    mp_candidates = {c["mp_app_id"]: c for c in data.get("mp_candidates", [])}
    cons_info = {c["cons_id"]: c for c in data.get("constituencies", [])}
    prov_info = {p["prov_id"]: p for p in data.get("provinces", {}).get("province", [])}

    stats = data.get("stats_cons", {})
    ref_stats = data.get("stats_referendum", {})

    # Build referendum lookup
    ref_by_cons = {}
    for province in ref_stats.get("result_province", []):
        for cons in province.get("constituencies", []):
            ref_by_cons[cons["cons_id"]] = cons

    lines = []

    # Header
    lines.append("╔" + "═" * 98 + "╗")
    lines.append("║" + "รายงานผลการเลือกตั้ง สส. ทั่วไป และประชามติ 2569".center(98) + "║")
    lines.append("║" + "THAILAND GENERAL ELECTION & REFERENDUM RESULTS 2569 BE (2026 CE)".center(98) + "║")
    lines.append("╠" + "═" * 98 + "╣")
    lines.append("║" + f"  ข้อมูล ณ: {data.get('fetched_at', 'N/A')}".ljust(98) + "║")
    lines.append("║" + f"  แหล่งข้อมูล: {data.get('source', 'N/A')}".ljust(98) + "║")
    lines.append("╚" + "═" * 98 + "╝")

    # Overall Election Statistics
    lines.append("\n")
    lines.append("┌" + "─" * 58 + "┐")
    lines.append("│" + " สถิติภาพรวม การเลือกตั้ง (Election Statistics)".ljust(58) + "│")
    lines.append("├" + "─" * 58 + "┤")
    lines.append("│" + f"  ผู้มีสิทธิเลือกตั้งทั้งหมด    {stats.get('turn_out', 0) and data.get('provinces', {}).get('total_registered_vote', 0):>15,}".ljust(58) + "│")
    lines.append("│" + f"  ผู้มาใช้สิทธิ (Turnout)      {stats.get('turn_out', 0):>15,}  ({stats.get('percent_turn_out', 0):>5.2f}%)".ljust(58) + "│")
    lines.append("│" + f"  บัตรดี (Valid)              {stats.get('valid_votes', 0):>15,}".ljust(58) + "│")
    lines.append("│" + f"  บัตรเสีย (Invalid)          {stats.get('invalid_votes', 0):>15,}".ljust(58) + "│")
    lines.append("│" + f"  บัตรไม่เลือกผู้ใด (Blank)    {stats.get('blank_votes', 0):>15,}".ljust(58) + "│")
    lines.append("└" + "─" * 58 + "┘")

    # Referendum Overall Statistics
    if ref_stats:
        lines.append("\n")
        lines.append("┌" + "─" * 58 + "┐")
        lines.append("│" + " สถิติภาพรวม ประชามติ (Referendum Statistics)".ljust(58) + "│")
        lines.append("├" + "─" * 58 + "┤")
        lines.append("│" + f"  ผู้มาใช้สิทธิ               {ref_stats.get('referendum_turn_out', 0):>15,}  ({ref_stats.get('referendum_percent_turn_out', 0):>5.2f}%)".ljust(58) + "│")
        lines.append("│" + f"  บัตรดี                     {ref_stats.get('referendum_valid_votes', 0):>15,}".ljust(58) + "│")
        lines.append("│" + f"  บัตรเสีย                   {ref_stats.get('referendum_invalid_votes', 0):>15,}".ljust(58) + "│")
        lines.append("├" + "─" * 58 + "┤")
        lines.append("│" + "  คำถาม: รัฐธรรมนูญฉบับใหม่".ljust(58) + "│")
        lines.append("├" + "─" * 58 + "┤")

        ref_results = ref_stats.get("referendum_results", {})
        for q_id, result in ref_results.items():
            lines.append("│" + f"  ✓ เห็นชอบ (YES)            {result.get('yes', 0):>15,}  ({result.get('percent_yes', 0):>5.2f}%)".ljust(58) + "│")
            lines.append("│" + f"  ✗ ไม่เห็นชอบ (NO)          {result.get('no', 0):>15,}  ({result.get('percent_no', 0):>5.2f}%)".ljust(58) + "│")
            lines.append("│" + f"  ○ ไม่แสดงความเห็น          {result.get('abstained', 0):>15,}  ({result.get('percent_abstained', 0):>5.2f}%)".ljust(58) + "│")
        lines.append("└" + "─" * 58 + "┘")

    # All Constituency Details
    lines.append("\n")
    lines.append("╔" + "═" * 98 + "╗")
    lines.append("║" + " ข้อมูลรายเขตเลือกตั้ง (Constituency Details) - ทุกเขต".center(98) + "║")
    lines.append("╚" + "═" * 98 + "╝")

    for province in stats.get("result_province", []):
        prov_id = province["prov_id"]
        prov_name = prov_info.get(prov_id, {}).get("province", prov_id)

        for cons in province.get("constituencies", []):
            cons_id = cons["cons_id"]
            cons_data = cons_info.get(cons_id, {})
            cons_no = cons_data.get("cons_no", 0)

            if cons_no == 0:
                continue

            zones = cons_data.get("zone", [])
            ref_cons = ref_by_cons.get(cons_id, {})
            registered = cons_data.get("registered_vote", 0)

            # Constituency Header
            lines.append("\n")
            lines.append("┏" + "━" * 98 + "┓")
            lines.append("┃" + f"  {prov_name} เขต {cons_no}".ljust(98) + "┃")
            lines.append("┣" + "━" * 98 + "┫")

            # Zone info (wrap long text)
            zone_text = ", ".join(zones) if zones else "-"
            if len(zone_text) > 90:
                zone_text = zone_text[:87] + "..."
            lines.append("┃" + f"  พื้นที่: {zone_text}".ljust(98) + "┃")
            lines.append("┃" + f"  ผู้มีสิทธิเลือกตั้ง: {registered:,}".ljust(98) + "┃")
            lines.append("┗" + "━" * 98 + "┛")

            # สส.แบ่งเขต Section
            lines.append("")
            lines.append("  ┌" + "─" * 94 + "┐")
            lines.append("  │" + " สส.แบ่งเขต (Constituency MP)".ljust(94) + "│")
            lines.append("  ├" + "─" * 94 + "┤")
            lines.append("  │" + f"  ผู้มาใช้สิทธิ: {cons.get('turn_out', 0):>10,} ({cons.get('percent_turn_out', 0):>5.2f}%)   │   บัตรดี: {cons.get('valid_votes', 0):>10,}   │   บัตรเสีย: {cons.get('invalid_votes', 0):>8,}   │   ไม่เลือกผู้ใด: {cons.get('blank_votes', 0):>8,}".ljust(94) + "│")
            lines.append("  ├" + "─" * 94 + "┤")
            lines.append("  │" + f"  {'ลำดับ':<6} {'ชื่อผู้สมัคร':<40} {'พรรค':<20} {'คะแนน':>12} {'%':>8}    ".ljust(94) + "│")
            lines.append("  ├" + "─" * 94 + "┤")

            candidates = sorted(cons.get("candidates", []), key=lambda x: x.get("mp_app_rank", 999))
            for c in candidates:
                mp_id = c.get("mp_app_id", "")
                mp_info = mp_candidates.get(mp_id, {})
                party_id = c.get("party_id", 0)
                party_info = parties_info.get(party_id, {})

                name = mp_info.get("mp_app_name", mp_id)
                party = party_info.get("name", "")
                votes = c.get("mp_app_vote", 0)
                pct = c.get("mp_app_vote_percent", 0)
                rank = c.get("mp_app_rank", 0)
                winner = " ★" if rank == 1 else "  "

                # Truncate long names
                name_display = name[:38] if len(name) > 38 else name
                party_display = party[:18] if len(party) > 18 else party

                lines.append("  │" + f" {winner}{rank:>3}.  {name_display:<40} {party_display:<20} {votes:>12,} {pct:>7.2f}%   ".ljust(94) + "│")

            lines.append("  └" + "─" * 94 + "┘")

            # บัญชีรายชื่อ Section
            lines.append("")
            lines.append("  ┌" + "─" * 94 + "┐")
            lines.append("  │" + " บัญชีรายชื่อ (Party List)".ljust(94) + "│")
            lines.append("  ├" + "─" * 94 + "┤")
            lines.append("  │" + f"  ผู้มาใช้สิทธิ: {cons.get('party_list_turn_out', 0):>10,} ({cons.get('party_list_percent_turn_out', 0):>5.2f}%)   │   บัตรดี: {cons.get('party_list_valid_votes', 0):>10,}   │   บัตรเสีย: {cons.get('party_list_invalid_votes', 0):>8,}   │   ไม่เลือกผู้ใด: {cons.get('party_list_blank_votes', 0):>8,}".ljust(94) + "│")
            lines.append("  ├" + "─" * 94 + "┤")
            lines.append("  │" + f"  {'ลำดับ':<6} {'พรรค':<50} {'คะแนน':>15} {'%':>10}       ".ljust(94) + "│")
            lines.append("  ├" + "─" * 94 + "┤")

            party_results = sorted(cons.get("result_party", []), key=lambda x: x.get("party_list_vote", 0), reverse=True)
            for i, pr in enumerate(party_results, 1):
                party_id = pr.get("party_id", 0)
                party_info = parties_info.get(party_id, {})
                party_name = party_info.get("name", f"Party {party_id}")
                votes = pr.get("party_list_vote", 0)
                pct = pr.get("party_list_vote_percent", 0)

                if votes == 0:
                    continue  # Skip parties with no votes

                party_display = party_name[:48] if len(party_name) > 48 else party_name
                lines.append("  │" + f"  {i:>4}.  {party_display:<50} {votes:>15,} {pct:>9.2f}%      ".ljust(94) + "│")

            lines.append("  └" + "─" * 94 + "┘")

            # ประชามติ Section
            lines.append("")
            lines.append("  ┌" + "─" * 94 + "┐")
            lines.append("  │" + " ประชามติ (Referendum)".ljust(94) + "│")
            lines.append("  ├" + "─" * 94 + "┤")
            lines.append("  │" + f"  ผู้มาใช้สิทธิ: {ref_cons.get('referendum_turn_out', 0):>10,} ({ref_cons.get('referendum_percent_turn_out', 0):>5.2f}%)   │   บัตรดี: {ref_cons.get('referendum_valid_votes', 0):>10,}   │   บัตรเสีย: {ref_cons.get('referendum_invalid_votes', 0):>8,}".ljust(94) + "│")
            lines.append("  ├" + "─" * 94 + "┤")

            ref_results = ref_cons.get("referendum_results", {})
            for q_id, result in ref_results.items():
                lines.append("  │" + f"  ✓ เห็นชอบ (YES)           {result.get('yes', 0):>12,}    ({result.get('percent_yes', 0):>6.2f}%)".ljust(94) + "│")
                lines.append("  │" + f"  ✗ ไม่เห็นชอบ (NO)         {result.get('no', 0):>12,}    ({result.get('percent_no', 0):>6.2f}%)".ljust(94) + "│")
                lines.append("  │" + f"  ○ ไม่แสดงความเห็น         {result.get('abstained', 0):>12,}    ({result.get('percent_abstained', 0):>6.2f}%)".ljust(94) + "│")

            lines.append("  └" + "─" * 94 + "┘")

    # Footer
    lines.append("\n")
    lines.append("╔" + "═" * 98 + "╗")
    lines.append("║" + " จบรายงาน (End of Report)".center(98) + "║")
    lines.append("╠" + "═" * 98 + "╣")
    lines.append("║" + "  ไฟล์ข้อมูลเพิ่มเติม:".ljust(98) + "║")
    lines.append("║" + "    • constituency_details.csv  - ข้อมูลผู้สมัครและคะแนนบัญชีรายชื่อรายเขต".ljust(98) + "║")
    lines.append("║" + "    • constituency_summary.csv  - สรุปรายเขต พร้อมผลประชามติ".ljust(98) + "║")
    lines.append("║" + "    • referendum_details.csv    - ผลประชามติรายเขต".ljust(98) + "║")
    lines.append("║" + "    • election_data.json        - ข้อมูลดิบทั้งหมด".ljust(98) + "║")
    lines.append("╚" + "═" * 98 + "╝")

    report = "\n".join(lines)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Saved: {filename}")
    return report


def main():
    # Fetch all data
    data = fetch_all_data()

    # Save raw JSON
    json_path = DATA_DIR / "election_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved: {json_path}")

    print("\nCreating formatted outputs...")

    # Create CSVs
    create_constituency_details_csv(data, DATA_DIR / "constituency_details.csv")
    create_referendum_details_csv(data, DATA_DIR / "referendum_details.csv")
    create_constituency_summary_csv(data, DATA_DIR / "constituency_summary.csv")

    # Create readable report
    report = create_readable_report(data, REPORTS_DIR / "election_report.txt")

    print("\n" + "=" * 50)
    print("FETCH COMPLETE!")
    print("=" * 50)
    print("\nOutput files:")
    print("  - data/election_data.json        (complete raw data)")
    print("  - data/constituency_details.csv  (all candidates & party-list per constituency)")
    print("  - data/referendum_details.csv    (referendum results per constituency)")
    print("  - data/constituency_summary.csv  (one row per constituency with all data)")
    print("  - reports/election_report.txt    (human-readable report)")

    # Print report
    print("\n" + report)


if __name__ == "__main__":
    main()
