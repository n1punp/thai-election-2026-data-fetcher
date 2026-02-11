#!/usr/bin/env python3
"""
ECT Election Index Fetcher
Extracts Google Drive folder links from the ECT election-2026 page.

Uses Playwright to render JavaScript content.

Usage:
    uv run --with playwright python src/fetch_ect_index.py

First time setup:
    uv run --with playwright python -m playwright install chromium
"""

import json
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote

# Paths
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

INDEX_FILE = DATA_DIR / "ect_election_index.json"

# Target URL
ECT_ELECTION_URL = "https://www.ect.go.th/ect_th/th/election-2026"


# Province name mapping (Thai to English slug for folder names)
PROVINCE_SLUGS = {
    "กรุงเทพมหานคร": "bangkok",
    "กรุงเทพ": "bangkok",
    "กระบี่": "krabi",
    "กาญจนบุรี": "kanchanaburi",
    "กาฬสินธุ์": "kalasin",
    "กำแพงเพชร": "kamphaengphet",
    "ขอนแก่น": "khonkaen",
    "จันทบุรี": "chanthaburi",
    "ฉะเชิงเทรา": "chachoengsao",
    "ชลบุรี": "chonburi",
    "ชัยนาท": "chainat",
    "ชัยภูมิ": "chaiyaphum",
    "ชุมพร": "chumphon",
    "เชียงราย": "chiangrai",
    "เชียงใหม่": "chiangmai",
    "ตรัง": "trang",
    "ตราด": "trat",
    "ตาก": "tak",
    "นครนายก": "nakhonnayok",
    "นครปฐม": "nakhonpathom",
    "นครพนม": "nakhonphanom",
    "นครราชสีมา": "nakhonratchasima",
    "นครศรีธรรมราช": "nakhonsithammarat",
    "นครสวรรค์": "nakhonsawan",
    "นนทบุรี": "nonthaburi",
    "นราธิวาส": "narathiwat",
    "น่าน": "nan",
    "บึงกาฬ": "buengkan",
    "บุรีรัมย์": "buriram",
    "ปทุมธานี": "pathumthani",
    "ประจวบคีรีขันธ์": "prachuapkhirikhan",
    "ปราจีนบุรี": "prachinburi",
    "ปัตตานี": "pattani",
    "พระนครศรีอยุธยา": "ayutthaya",
    "อยุธยา": "ayutthaya",
    "พังงา": "phangnga",
    "พัทลุง": "phatthalung",
    "พิจิตร": "phichit",
    "พิษณุโลก": "phitsanulok",
    "เพชรบุรี": "phetchaburi",
    "เพชรบูรณ์": "phetchabun",
    "แพร่": "phrae",
    "พะเยา": "phayao",
    "ภูเก็ต": "phuket",
    "มหาสารคาม": "mahasarakham",
    "มุกดาหาร": "mukdahan",
    "แม่ฮ่องสอน": "maehongson",
    "ยโสธร": "yasothon",
    "ยะลา": "yala",
    "ร้อยเอ็ด": "roiet",
    "ระนอง": "ranong",
    "ระยอง": "rayong",
    "ราชบุรี": "ratchaburi",
    "ลพบุรี": "lopburi",
    "ลำปาง": "lampang",
    "ลำพูน": "lamphun",
    "เลย": "loei",
    "ศรีสะเกษ": "sisaket",
    "สกลนคร": "sakonnakhon",
    "สงขลา": "songkhla",
    "สตูล": "satun",
    "สมุทรปราการ": "samutprakan",
    "สมุทรสงคราม": "samutsongkhram",
    "สมุทรสาคร": "samutsakhon",
    "สระแก้ว": "sakaeo",
    "สระบุรี": "saraburi",
    "สิงห์บุรี": "singburi",
    "สุโขทัย": "sukhothai",
    "สุพรรณบุรี": "suphanburi",
    "สุราษฎร์ธานี": "suratthani",
    "สุรินทร์": "surin",
    "หนองคาย": "nongkhai",
    "หนองบัวลำภู": "nongbualamphu",
    "อ่างทอง": "angthong",
    "อำนาจเจริญ": "amnatcharoen",
    "อุดรธานี": "udonthani",
    "อุตรดิตถ์": "uttaradit",
    "อุทัยธานี": "uthaithani",
    "อุบลราชธานี": "ubonratchathani",
}

# Regions to skip (not provinces)
REGIONS = {
    "ภาคเหนือ",
    "ภาคกลาง",
    "ภาคตะวันออกเฉียงเหนือ",
    "ภาคอีสาน",
    "ภาคตะวันออก",
    "ภาคตะวันตก",
    "ภาคใต้",
}


def is_region(text: str) -> bool:
    """Check if text is a region name (not a province)."""
    text = text.strip()
    if text in REGIONS:
        return True
    # Also check if it contains region keywords
    if "ภาค" in text and any(
        r in text for r in ["เหนือ", "กลาง", "ใต้", "ออก", "ตก", "อีสาน"]
    ):
        return True
    return False


def extract_province_from_text(text: str) -> tuple[str, str]:
    print(f"extract_province_from_text: {text}")
    """Extract province name from text. Returns (thai_name, english_slug)."""
    text = text.strip()

    # Skip if it's a region
    if is_region(text):
        return "", ""

    # Check for exact match first
    if text in PROVINCE_SLUGS:
        return text, PROVINCE_SLUGS[text]

    # Check if any province name is contained in the text
    for thai_name, slug in PROVINCE_SLUGS.items():
        if thai_name in text:
            return thai_name, slug

    return "", ""


def extract_label_from_img(img_src: str) -> tuple[str, str, str]:
    """Extract province/region name from image URL. Returns (label, thai_name, english_slug)."""
    # Decode URL-encoded Thai text
    decoded = unquote(img_src)

    # Extract path components that might contain province names
    # e.g., /รายงานผลคะแนน ภาคเหนือ/1.png
    parts = decoded.split("/")

    for part in reversed(parts):
        # Skip filename
        if re.match(r"^\d+\.(png|jpg|jpeg|gif)$", part, re.IGNORECASE):
            continue

        thai_name, slug = extract_province_from_text(part)
        if slug:
            return part, thai_name, slug

    # Try to extract from filename
    match = re.search(r"/([^/]+)\.(png|jpg|jpeg|gif)$", decoded, re.IGNORECASE)
    if match:
        name = match.group(1)
        name = re.sub(r"^\d+[.\-_]?", "", name)  # Remove leading numbers
        thai_name, slug = extract_province_from_text(name)
        if slug:
            return name, thai_name, slug
        return name.strip(), "", ""

    return "", "", ""


def fetch_gdrive_links_playwright():
    """Fetch Google Drive links using Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Run:")
        print("  uv run --with playwright python -m playwright install chromium")
        return []

    print(f"Fetching: {ECT_ELECTION_URL}")
    print("Using Playwright to render JavaScript...")

    links = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(ECT_ELECTION_URL, wait_until="networkidle", timeout=60000)

            # Wait a bit for any lazy-loaded content
            page.wait_for_timeout(2000)

            # Find all anchor tags with Google Drive links
            anchors = page.query_selector_all('a[href*="drive.google.com"]')

            print(f"Found {len(anchors)} Google Drive links")

            seen_ids = set()

            for anchor in anchors:
                href = anchor.get_attribute("href")
                if not href:
                    continue

                # Extract folder ID
                folder_match = re.search(r"/folders/([a-zA-Z0-9_-]+)", href)
                file_match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", href)

                item_id = None
                item_type = None

                if folder_match:
                    item_id = folder_match.group(1)
                    item_type = "folder"
                elif file_match:
                    item_id = file_match.group(1)
                    item_type = "file"

                if not item_id or item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                # Find province name from nearby <span> element
                province_th = ""
                province_en = ""
                label = ""

                # Find province name from parent <td> cell
                # Structure: <td><p><span>Province</span></p><p><a>link</a></p></td>
                span_texts = page.evaluate(
                    """(anchor) => {
                    let td = anchor.closest('td');
                    if (td) {
                        const spans = td.querySelectorAll('span');
                        const texts = [];
                        for (const span of spans) {
                            const text = span.innerText;
                            // Only include short Thai text (likely province names)
                            if (text && text.length >= 2 && text.length <= 60) {
                                if (/[\u0e00-\u0e7f]/.test(text)) {
                                    texts.push(text);
                                }
                            }
                        }
                        return texts;
                    }
                    return [];
                }""",
                    anchor,
                )

                # Find first valid province from span texts (skip regions)
                for text in span_texts:
                    if is_region(text):
                        continue
                    th, en = extract_province_from_text(text)
                    if en:
                        province_th = th
                        province_en = en
                        label = text
                        break

                url = (
                    f"https://drive.google.com/drive/folders/{item_id}"
                    if item_type == "folder"
                    else f"https://drive.google.com/file/d/{item_id}"
                )

                links.append(
                    {
                        "type": item_type,
                        "id": item_id,
                        "url": url,
                        "label": label,
                        "province_th": province_th,
                        "province_en": province_en,
                    }
                )

                display_name = province_en or province_th or label or "unknown"
                print(
                    f"  - {item_type.capitalize()}: {item_id[:15]}... -> {display_name}"
                )

        except Exception as e:
            print(f"Error: {e}")
            import traceback

            traceback.print_exc()

        finally:
            browser.close()

    return links


def main():
    print("=" * 60)
    print("ECT Election Index Fetcher")
    print("=" * 60)

    links = fetch_gdrive_links_playwright()

    if not links:
        print("\nNo Google Drive links found!")
        return

    # Create index
    index = {
        "fetched_at": datetime.now().isoformat(),
        "source": ECT_ELECTION_URL,
        "total_folders": len([l for l in links if l["type"] == "folder"]),
        "total_files": len([l for l in links if l["type"] == "file"]),
        "links": links,
    }

    # Save index
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Index saved: {INDEX_FILE}")
    print(f"Total folders: {index['total_folders']}")
    print(f"Total files: {index['total_files']}")


if __name__ == "__main__":
    main()
