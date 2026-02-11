#!/usr/bin/env python3
"""
ECT Election PDF Fetcher
Downloads election result PDFs from Google Drive folders.
Source: https://www.ect.go.th/ect_th/th/election-2026

Usage:
    # First create index using fetch_ect_index.py
    uv run --with playwright python src/fetch_ect_index.py

    # Download PDFs (supports resume)
    uv run --with gdown python src/fetch_ect_pdfs.py --download

    # Download with longer timeout
    uv run --with gdown python src/fetch_ect_pdfs.py --download --timeout 180
"""

import json
import re
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
import threading


# Paths
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
PDF_DIR = ROOT_DIR / "pdfs"

# State files for resume support
INDEX_FILE = DATA_DIR / "ect_election_index.json"
PROGRESS_FILE = DATA_DIR / "download_progress.json"
ERRORS_FILE = DATA_DIR / "download_errors.json"

# Ensure directories exist
PDF_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# ECT Base URLs
ECT_BASE = "https://www.ect.go.th"

# Thread-safe lock for progress updates
progress_lock = threading.Lock()

# Thai province names with their URL slugs
PROVINCES = {
    "กรุงเทพมหานคร": "bangkok",
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

DOWNLOAD_PATTERNS = [
    "/th/{slug}/db_181_{slug}_download_34",
    "/th/{slug}/db_181_{slug}_download_32",
    "/th/{slug}/download",
    "/th/{slug}/news",
]


def get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "th,en;q=0.9",
    }


def fetch_page(url: str, client: httpx.Client) -> str | None:
    try:
        resp = client.get(url, follow_redirects=True, timeout=30)
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception:
        return None


def extract_google_drive_links(html: str) -> list:
    links = []
    seen_ids = set()

    folder_patterns = [
        r'https://drive\.google\.com/drive/folders/([a-zA-Z0-9_-]+)',
        r'https://drive\.google\.com/drive/u/\d+/folders/([a-zA-Z0-9_-]+)',
    ]

    for pattern in folder_patterns:
        for folder_id in re.findall(pattern, html):
            if folder_id not in seen_ids:
                seen_ids.add(folder_id)
                links.append({
                    "type": "folder",
                    "id": folder_id,
                    "url": f"https://drive.google.com/drive/folders/{folder_id}"
                })

    file_patterns = [
        r'https://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)',
        r'https://drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)',
    ]

    for pattern in file_patterns:
        for file_id in re.findall(pattern, html):
            if file_id not in seen_ids:
                seen_ids.add(file_id)
                links.append({
                    "type": "file",
                    "id": file_id,
                    "url": f"https://drive.google.com/file/d/{file_id}"
                })

    soup = BeautifulSoup(html, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)

        if 'drive.google.com' in href:
            folder_match = re.search(r'/folders/([a-zA-Z0-9_-]+)', href)
            file_match = re.search(r'/d/([a-zA-Z0-9_-]+)', href)

            if folder_match and folder_match.group(1) not in seen_ids:
                seen_ids.add(folder_match.group(1))
                links.append({
                    "type": "folder",
                    "id": folder_match.group(1),
                    "url": f"https://drive.google.com/drive/folders/{folder_match.group(1)}",
                    "text": text
                })
            elif file_match and file_match.group(1) not in seen_ids:
                seen_ids.add(file_match.group(1))
                links.append({
                    "type": "file",
                    "id": file_match.group(1),
                    "url": f"https://drive.google.com/file/d/{file_match.group(1)}",
                    "text": text
                })

    return links


def extract_pdf_links(html: str, base_url: str) -> list:
    pdfs = []
    soup = BeautifulSoup(html, 'html.parser')

    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.lower().endswith('.pdf'):
            full_url = urljoin(base_url, href)
            pdfs.append({
                "url": full_url,
                "text": a.get_text(strip=True),
                "filename": os.path.basename(urlparse(href).path)
            })

    return pdfs


def process_province(slug: str, thai_name: str, client: httpx.Client) -> dict:
    result = {
        "province_th": thai_name,
        "province_en": slug,
        "google_drive_links": [],
        "pdf_links": [],
        "pages_checked": []
    }

    province_base = f"{ECT_BASE}/{slug}"

    html = fetch_page(province_base, client)
    if html:
        result["pages_checked"].append(province_base)
        result["google_drive_links"].extend(extract_google_drive_links(html))
        result["pdf_links"].extend(extract_pdf_links(html, province_base))

    for pattern in DOWNLOAD_PATTERNS:
        url = ECT_BASE + pattern.format(slug=slug)
        html = fetch_page(url, client)
        if html:
            result["pages_checked"].append(url)
            new_gdrive = extract_google_drive_links(html)
            new_pdfs = extract_pdf_links(html, url)

            existing_ids = {l["id"] for l in result["google_drive_links"]}
            for link in new_gdrive:
                if link["id"] not in existing_ids:
                    result["google_drive_links"].append(link)
                    existing_ids.add(link["id"])

            existing_urls = {l["url"] for l in result["pdf_links"]}
            for link in new_pdfs:
                if link["url"] not in existing_urls:
                    result["pdf_links"].append(link)

    return result


# === Progress & Error Tracking ===

def load_progress() -> dict:
    """Load download progress for resume support."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed_folders": [], "completed_files": [], "last_updated": None}


def save_progress(progress: dict):
    """Save download progress."""
    progress["last_updated"] = datetime.now().isoformat()
    with progress_lock:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)


def load_errors() -> dict:
    """Load error log."""
    if ERRORS_FILE.exists():
        with open(ERRORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"errors": [], "last_updated": None}


def save_errors(errors: dict):
    """Save error log."""
    errors["last_updated"] = datetime.now().isoformat()
    with progress_lock:
        with open(ERRORS_FILE, "w", encoding="utf-8") as f:
            json.dump(errors, f, ensure_ascii=False, indent=2)


def log_error(errors: dict, error_type: str, province: str, folder_id: str,
              url: str, message: str):
    """Log a download error."""
    errors["errors"].append({
        "timestamp": datetime.now().isoformat(),
        "type": error_type,
        "province": province,
        "folder_id": folder_id,
        "url": url,
        "message": message
    })
    save_errors(errors)


# === Download Functions ===

def download_file_direct(file_id: str, output_dir: Path, client: httpx.Client) -> tuple[bool, str]:
    """Download a single file from Google Drive."""
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    try:
        resp = client.get(download_url, follow_redirects=True, timeout=60)

        if resp.status_code == 200:
            # Check for virus scan warning page
            if b'download_warning' in resp.content or b'confirm=' in resp.content:
                confirm_match = re.search(r'confirm=([a-zA-Z0-9_-]+)', resp.text)
                if confirm_match:
                    confirm_url = f"{download_url}&confirm={confirm_match.group(1)}"
                    resp = client.get(confirm_url, follow_redirects=True, timeout=60)

            # Get filename from headers or use file_id
            content_disp = resp.headers.get('content-disposition', '')
            filename_match = re.search(r'filename\*?=(?:UTF-8\'\')?([^;\n]+)', content_disp)
            if filename_match:
                filename = filename_match.group(1).strip('"\'')
            else:
                filename = f"{file_id}.pdf"

            # Check if it's actually a PDF
            if resp.content[:4] == b'%PDF' or 'application/pdf' in resp.headers.get('content-type', ''):
                output_path = output_dir / filename
                with open(output_path, 'wb') as f:
                    f.write(resp.content)
                return True, filename
            else:
                return False, "Not a PDF or access denied"
        else:
            return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


def download_folder_with_timeout(folder_id: str, output_dir: Path, timeout_sec: int = 120,
                                  province: str = "") -> tuple[list, str]:
    """Download folder with timeout using subprocess. Shows real-time progress."""
    import subprocess
    import time

    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"

    # Create a Python script to run gdown with output
    script = f'''
import gdown
import sys
folder_url = "{folder_url}"
output_dir = "{output_dir}"
try:
    files = gdown.download_folder(
        folder_url,
        output=output_dir,
        quiet=False,
        use_cookies=False,
        remaining_ok=True
    )
    if files:
        print(f"\\n__SUCCESS__:{{len(files)}}")
        for f in files:
            print(f"__FILE__:{{f}}")
    else:
        print("\\n__SUCCESS__:0")
except Exception as e:
    print(f"\\n__ERROR__:{{e}}")
'''

    # Run in subprocess with real-time output
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    start_time = time.time()
    last_output_time = start_time
    output_lines = []
    files_downloaded = []
    error_msg = ""

    import select

    try:
        while True:
            elapsed = time.time() - start_time

            # Check timeout
            if elapsed > timeout_sec:
                proc.kill()
                print(f"\n    ✗ Timeout after {timeout_sec}s", flush=True)
                return [], f"Timeout after {timeout_sec}s"

            # Check if there's output available (non-blocking)
            ready, _, _ = select.select([proc.stdout], [], [], 1.0)

            if ready:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break

                if line:
                    last_output_time = time.time()
                    line = line.rstrip()
                    output_lines.append(line)

                    # Parse special markers
                    if line.startswith("__SUCCESS__:"):
                        pass  # Success marker
                    elif line.startswith("__FILE__:"):
                        filepath = line[9:]
                        files_downloaded.append(filepath)
                        filename = os.path.basename(filepath)
                        print(f"    ✓ {filename}", flush=True)
                    elif line.startswith("__ERROR__:"):
                        error_msg = line[10:]
                        print(f"    ✗ Error: {error_msg}", flush=True)
                    elif line.strip():
                        # Show all non-empty output from gdown
                        print(f"    {line}", flush=True)
            else:
                # No output available, show waiting indicator
                if proc.poll() is not None:
                    break
                silent_time = time.time() - last_output_time
                print(f"\r    Waiting... ({int(elapsed)}s elapsed, {int(silent_time)}s since last output)", end="", flush=True)

    except Exception as e:
        error_msg = str(e)
        print(f"\n    ✗ Exception: {e}", flush=True)

    # Wait for process to finish
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

    if error_msg:
        return [], error_msg

    return files_downloaded, ""


def download_folder_with_gdown(folder_id: str, output_dir: Path, province: str,
                                progress: dict, errors: dict, timeout: int = 120) -> tuple[int, int]:
    """Download folder using gdown with error handling and timeout."""
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"

    files, error_msg = download_folder_with_timeout(folder_id, output_dir, timeout, province)

    if files:
        return len(files), 0

    if error_msg:
        # Categorize error
        if "Too many files" in error_msg or "50" in error_msg:
            error_type = "too_many_files"
        elif "Access" in error_msg or "permission" in error_msg.lower():
            error_type = "access_denied"
        elif "quota" in error_msg.lower():
            error_type = "quota_exceeded"
        elif "Timeout" in error_msg:
            error_type = "timeout"
        else:
            error_type = "download_error"

        log_error(errors, error_type, province, folder_id, folder_url, error_msg)
        return 0, 1

    return 0, 0


def download_worker(task: dict, progress: dict, errors: dict, timeout: int = 120) -> dict:
    """Worker function for parallel downloads."""
    province = task["province"]
    folder = task["folder"]
    folder_id = folder["id"]
    output_dir = task["output_dir"]

    # Skip if already completed
    if folder_id in progress["completed_folders"]:
        return {"province": province, "folder_id": folder_id, "downloaded": 0, "skipped": True}

    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded, failed = download_folder_with_gdown(
        folder_id, output_dir, province, progress, errors, timeout=timeout
    )

    # Only mark as completed if successful (failed downloads can be retried)
    if downloaded > 0 or failed == 0:
        with progress_lock:
            progress["completed_folders"].append(folder_id)
            save_progress(progress)

    return {
        "province": province,
        "folder_id": folder_id,
        "downloaded": downloaded,
        "failed": failed,
        "skipped": False
    }


# === Main Functions ===

def create_index(provinces_to_process: list = None):
    """Create index of Google Drive links from ECT websites."""
    print("=" * 60)
    print("ECT Election PDF Fetcher - Creating Index")
    print("=" * 60)

    results = {
        "fetched_at": datetime.now().isoformat(),
        "source": "https://www.ect.go.th/ect_th/th/election-2026",
        "provinces": []
    }

    provinces = [(v, k) for k, v in PROVINCES.items()]
    if provinces_to_process:
        provinces = [(slug, name) for slug, name in provinces if slug in provinces_to_process]

    with httpx.Client(headers=get_headers(), timeout=30) as client:
        for i, (slug, thai_name) in enumerate(provinces, 1):
            print(f"[{i}/{len(provinces)}] {thai_name} ({slug})", end=" ")
            sys.stdout.flush()

            province_result = process_province(slug, thai_name, client)
            results["provinces"].append(province_result)

            gdrive_count = len(province_result["google_drive_links"])
            pdf_count = len(province_result["pdf_links"])
            print(f"-> {gdrive_count} folders, {pdf_count} PDFs")

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nIndex saved: {INDEX_FILE}")

    total_gdrive = sum(len(p["google_drive_links"]) for p in results["provinces"])
    total_pdfs = sum(len(p["pdf_links"]) for p in results["provinces"])

    print(f"\nTotal: {total_gdrive} Google Drive folders, {total_pdfs} direct PDFs")

    return results


def download_pdfs(retry_errors: bool = False, timeout: int = 120):
    """Download PDFs sequentially with resume support."""

    if not INDEX_FILE.exists():
        print(f"Index not found: {INDEX_FILE}")
        print("Run: uv run --with playwright python src/fetch_ect_index.py")
        return

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index = json.load(f)

    progress = load_progress()
    errors = load_errors()

    # Clear errors if retrying
    if retry_errors:
        errors = {"errors": [], "last_updated": None}
        save_errors(errors)

    print("=" * 60)
    print("ECT Election PDF Fetcher - Downloading")
    print("=" * 60)
    print(f"Timeout: {timeout}s per folder")
    print(f"Already completed: {len(progress['completed_folders'])} folders")
    if progress.get('last_updated'):
        print(f"Last run: {progress['last_updated']}")
    print()

    # Build task list - support both old and new index formats
    tasks = []

    # New format: index["links"] is a flat list
    if "links" in index:
        for link in index["links"]:
            if link["type"] == "folder" and link["id"] not in progress["completed_folders"]:
                # Use province_th > label > province_en > ID for folder name (prefer Thai)
                folder_name = (
                    link.get("province_th") or
                    link.get("label") or
                    link.get("province_en") or
                    link["id"][:20]
                )
                # Sanitize for filesystem (keep Thai characters, remove invalid chars)
                safe_name = re.sub(r'[<>:"/\\|?*]', '_', folder_name)
                tasks.append({
                    "province": safe_name,
                    "folder": link,
                    "output_dir": PDF_DIR / safe_name
                })
    # Old format: index["provinces"] with nested links
    elif "provinces" in index:
        for prov in index["provinces"]:
            # Prefer Thai name for folder
            folder_name = prov.get("province_th") or prov.get("province_en")
            folders = [l for l in prov["google_drive_links"] if l["type"] == "folder"]
            for folder in folders:
                if folder["id"] not in progress["completed_folders"]:
                    tasks.append({
                        "province": folder_name,
                        "folder": folder,
                        "output_dir": PDF_DIR / folder_name
                    })

    if not tasks:
        print("All folders already downloaded!")
        print(f"To re-download, delete {PROGRESS_FILE}")
        return

    print(f"Folders to download: {len(tasks)}")
    print("-" * 60)

    total_downloaded = 0
    total_failed = 0
    total_skipped = 0

    try:
        for i, task in enumerate(tasks, 1):
            province = task['province']
            folder_id = task['folder']['id']

            print(f"\n[{i}/{len(tasks)}] {province}")
            print(f"  Folder: {folder_id}")
            print(f"  Output: {task['output_dir']}")
            sys.stdout.flush()

            result = download_worker(task, progress, errors, timeout=timeout)

            if result["skipped"]:
                print("  Status: SKIPPED (already downloaded)")
                total_skipped += 1
            elif result.get("failed", 0) > 0:
                print("  Status: FAILED")
                total_failed += 1
            else:
                print(f"  Status: SUCCESS ({result['downloaded']} files)")
                total_downloaded += result["downloaded"]

    except KeyboardInterrupt:
        print("\n\nDownload interrupted! Progress saved.")
        print(f"Resume by running the same command again.")
        save_progress(progress)
        save_errors(errors)
        return

    # Final save
    save_progress(progress)
    save_errors(errors)

    # Summary
    print("\n" + "=" * 60)
    print("DOWNLOAD COMPLETE")
    print("=" * 60)
    print(f"Files downloaded: {total_downloaded}")
    print(f"Folders failed: {total_failed}")
    print(f"Folders skipped: {total_skipped}")
    print(f"\nProgress saved: {PROGRESS_FILE}")

    if errors["errors"]:
        print(f"Errors logged: {ERRORS_FILE} ({len(errors['errors'])} errors)")

        # Summarize errors by type
        error_types = {}
        for e in errors["errors"]:
            t = e.get("type", "unknown")
            error_types[t] = error_types.get(t, 0) + 1

        print("\nError summary:")
        for t, count in sorted(error_types.items(), key=lambda x: -x[1]):
            print(f"  {t}: {count}")


def show_errors():
    """Display download errors."""
    if not ERRORS_FILE.exists():
        print("No errors logged.")
        return

    errors = load_errors()

    if not errors["errors"]:
        print("No errors logged.")
        return

    print(f"Download Errors ({len(errors['errors'])} total)")
    print("=" * 60)

    for e in errors["errors"]:
        print(f"\n[{e['type']}] {e['province']}")
        print(f"  Folder: {e['folder_id']}")
        print(f"  URL: {e['url']}")
        print(f"  Error: {e['message'][:100]}")


def reset_progress():
    """Reset download progress to start fresh."""
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        print(f"Deleted: {PROGRESS_FILE}")
    if ERRORS_FILE.exists():
        ERRORS_FILE.unlink()
        print(f"Deleted: {ERRORS_FILE}")
    print("Progress reset. Next download will start fresh.")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch election PDFs from ECT provincial websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download PDFs
  python src/fetch_ect_pdfs.py --download

  # Download with longer timeout
  python src/fetch_ect_pdfs.py --download --timeout 180

  # Show failed downloads
  python src/fetch_ect_pdfs.py --show-errors

  # Reset and start fresh
  python src/fetch_ect_pdfs.py --reset
        """
    )
    parser.add_argument("--download", action="store_true",
                        help="Download PDFs from indexed folders")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Timeout per folder in seconds (default: 120)")
    parser.add_argument("--show-errors", action="store_true",
                        help="Show download errors")
    parser.add_argument("--retry-errors", action="store_true",
                        help="Clear error log and retry failed downloads")
    parser.add_argument("--reset", action="store_true",
                        help="Reset download progress")

    args = parser.parse_args()

    if args.show_errors:
        show_errors()
    elif args.reset:
        reset_progress()
    elif args.download:
        download_pdfs(retry_errors=args.retry_errors, timeout=args.timeout)
    else:
        print("Usage: python src/fetch_ect_pdfs.py --download")
        print("\nFirst create index using:")
        print("  uv run --with playwright python src/fetch_ect_index.py")


if __name__ == "__main__":
    main()
