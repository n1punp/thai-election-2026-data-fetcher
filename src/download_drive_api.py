#!/usr/bin/env python3
"""
Google Drive Folder Downloader using Drive API.
Downloads all files from folders in a single step with incremental progress.

Setup:
    1. Go to https://console.cloud.google.com/
    2. Create/select a project, enable "Google Drive API"
    3. Create API key: APIs & Services > Credentials > Create Credentials > API Key
    4. Set GOOGLE_API_KEY environment variable or create .env file

Usage:
    uv run --with google-api-python-client,requests python src/download_drive_api.py
    uv run --with google-api-python-client,requests python src/download_drive_api.py --province สระบุรี
    uv run --with google-api-python-client,requests python src/download_drive_api.py --folder 1YFrEvow3-HwkcosJuXNeI82DL1WSrK_S
    uv run --with google-api-python-client,requests python src/download_drive_api.py --workers 4
"""

import json
import os
import re
import argparse
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("Run: uv run --with google-api-python-client,requests python src/download_drive_api.py")
    exit(1)


ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
PDF_DIR = ROOT_DIR / "pdfs"

PDF_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

FOLDER_INDEX_FILE = DATA_DIR / "ect_election_index.json"
PROGRESS_FILE = DATA_DIR / "download_progress.json"
ENV_FILE = ROOT_DIR / ".env"

# Thread lock for progress file
progress_lock = threading.Lock()


def get_api_key() -> str:
    """Get API key from environment or .env file."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return api_key

    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                if line.startswith("GOOGLE_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"\'')
    return ""


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data.get("failed"), list):
                data["failed"] = {}
            return data
    return {"downloaded": [], "failed": {}, "errors": [], "last_updated": None}


def save_progress(progress: dict):
    progress["last_updated"] = datetime.now().isoformat()
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def download_file(file_id: str, output_path: Path, api_key: str) -> tuple[bool, str]:
    """Download file using direct URL with API key."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={api_key}"

    try:
        response = requests.get(url, stream=True, timeout=120)

        if response.status_code == 200:
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            if output_path.exists() and output_path.stat().st_size > 0:
                return True, ""
            else:
                output_path.unlink(missing_ok=True)
                return False, "Empty file"
        elif response.status_code == 403:
            return False, "Access denied"
        elif response.status_code == 404:
            return False, "Not found"
        elif response.status_code == 429:
            return False, "Rate limited"
        else:
            return False, f"HTTP {response.status_code}"

    except requests.Timeout:
        output_path.unlink(missing_ok=True)
        return False, "Timeout"
    except Exception as e:
        output_path.unlink(missing_ok=True)
        return False, str(e)[:50]


def list_files_recursive(service, folder_id: str, province: str, path: str = "") -> list:
    """Recursively list all files in a folder."""
    files = []
    page_token = None

    while True:
        try:
            query = f"'{folder_id}' in parents and trashed = false"
            results = service.files().list(
                q=query,
                pageSize=1000,
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()

            items = results.get("files", [])

            for item in items:
                item_id = item["id"]
                item_name = item["name"]
                item_path = f"{path}/{item_name}" if path else item_name
                mime_type = item.get("mimeType", "")

                if mime_type == "application/vnd.google-apps.folder":
                    print(f"  📁 {item_path}/", flush=True)
                    sub_files = list_files_recursive(service, item_id, province, item_path)
                    files.extend(sub_files)
                else:
                    files.append({
                        "id": item_id,
                        "name": item_name,
                        "path": item_path,
                        "province": province,
                        "size": int(item.get("size", 0)),
                    })

            page_token = results.get("nextPageToken")
            if not page_token:
                break

        except HttpError as e:
            print(f"  ✗ API Error listing {folder_id}: {e}", flush=True)
            break

    return files


def download_worker(file_info: dict, api_key: str, progress: dict, stats: dict) -> dict:
    """Worker function to download a single file."""
    file_id = file_info["id"]
    file_path = file_info["path"]
    province = file_info["province"]
    output_path = PDF_DIR / province / file_path

    # Check if already exists
    if output_path.exists() and output_path.stat().st_size > 0:
        with progress_lock:
            if file_id not in progress["downloaded"]:
                progress["downloaded"].append(file_id)
                save_progress(progress)
            stats["skipped"] += 1
        return {"id": file_id, "status": "skipped", "path": file_path}

    # Download
    success, error = download_file(file_id, output_path, api_key)

    with progress_lock:
        if success:
            size_kb = output_path.stat().st_size / 1024
            progress["downloaded"].append(file_id)
            if file_id in progress["failed"]:
                del progress["failed"][file_id]
            stats["downloaded"] += 1
            save_progress(progress)
            return {"id": file_id, "status": "success", "path": file_path, "size_kb": size_kb}
        else:
            progress["failed"][file_id] = {
                "path": file_path,
                "province": province,
                "error": error,
            }
            stats["failed"] += 1
            save_progress(progress)
            return {"id": file_id, "status": "failed", "path": file_path, "error": error}


def main():
    parser = argparse.ArgumentParser(description="Download Google Drive folders")
    parser.add_argument("--province", type=str, help="Download specific province only")
    parser.add_argument("--folder", type=str, help="Download specific folder ID")
    parser.add_argument("--reset", action="store_true", help="Reset progress")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--skip-failed", action="store_true", help="Skip previously failed files")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel downloads (default: 1)")
    args = parser.parse_args()

    if args.reset:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
        print("Progress reset.")
        return

    progress = load_progress()

    if args.status:
        print("=" * 60)
        print("Download Status")
        print("=" * 60)
        print(f"Downloaded: {len(progress.get('downloaded', []))}")
        failed = progress.get("failed", {})
        if isinstance(failed, dict):
            print(f"Failed: {len(failed)}")
            if failed:
                print("\nFailed files:")
                for fid, info in list(failed.items())[:10]:
                    print(f"  - {info.get('province')}/{info.get('path')}: {info.get('error')}")
        errors = progress.get("errors", [])
        if errors:
            print(f"\nErrors: {len(errors)}")
            for err in errors[-5:]:
                print(f"  - {err.get('province')}: {err.get('error', '')[:50]}")
        return

    api_key = get_api_key()
    if not api_key:
        print("=" * 60)
        print("Google Drive API Key Required")
        print("=" * 60)
        print("\n1. Go to https://console.cloud.google.com/")
        print("2. Create/select a project")
        print("3. Enable 'Google Drive API'")
        print("4. Create API key: APIs & Services > Credentials > Create Credentials > API Key")
        print("\nThen either:")
        print("  export GOOGLE_API_KEY=your_api_key")
        print("  OR create .env file with: GOOGLE_API_KEY=your_api_key")
        return

    # Build folder list
    if args.folder:
        folders = [{"id": args.folder, "province": args.province or "unknown"}]
    else:
        if not FOLDER_INDEX_FILE.exists():
            print(f"Folder index not found: {FOLDER_INDEX_FILE}")
            print("Run: uv run --with playwright python src/fetch_ect_index.py")
            print("Or specify --folder directly")
            return

        with open(FOLDER_INDEX_FILE, "r", encoding="utf-8") as f:
            folder_index = json.load(f)

        folders = []
        if "links" in folder_index:
            for link in folder_index["links"]:
                if link["type"] == "folder":
                    province_name = (
                        link.get("province_th")
                        or link.get("label")
                        or link.get("province_en")
                        or link["id"][:20]
                    )
                    province_name = re.sub(r'[<>:"/\\|?*]', "_", province_name)

                    if args.province and args.province.lower() not in province_name.lower():
                        continue

                    folders.append({"id": link["id"], "province": province_name})

    if not folders:
        print("No folders to download!")
        return

    # Build Drive service
    service = build("drive", "v3", developerKey=api_key)

    print("=" * 60)
    print("Google Drive Folder Downloader (API)")
    print("=" * 60)
    print(f"Folders: {len(folders)}")
    print(f"Already downloaded: {len(progress.get('downloaded', []))}")
    print(f"Workers: {args.workers}")
    if args.skip_failed:
        print(f"Skipping failed: {len(progress.get('failed', {}))}")
    print(f"Output: {PDF_DIR}")
    print("-" * 60)

    # Collect all files first
    print("\nListing files...")
    all_files = []
    for i, folder in enumerate(folders, 1):
        folder_id = folder["id"]
        province = folder["province"]
        print(f"\n[{i}/{len(folders)}] {province}")
        files = list_files_recursive(service, folder_id, province)
        all_files.extend(files)
        print(f"  Found {len(files)} files")

    print(f"\nTotal files found: {len(all_files)}")

    # Filter out already downloaded and optionally failed
    downloaded_set = set(progress.get("downloaded", []))
    failed_set = set(progress.get("failed", {}).keys()) if args.skip_failed else set()

    files_to_download = [
        f for f in all_files
        if f["id"] not in downloaded_set and f["id"] not in failed_set
    ]

    print(f"Files to download: {len(files_to_download)}")
    print("-" * 60)

    if not files_to_download:
        print("Nothing to download!")
        return

    stats = {"total": len(all_files), "downloaded": 0, "skipped": 0, "failed": 0}

    # Download with workers
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(download_worker, f, api_key, progress, stats): f
                for f in files_to_download
            }

            for future in as_completed(futures):
                result = future.result()
                if result["status"] == "success":
                    print(f"  ✓ {result['path']} ({result.get('size_kb', 0):.1f} KB)")
                elif result["status"] == "failed":
                    print(f"  ✗ {result['path']} ({result.get('error', 'unknown')})")
                    if "rate" in result.get("error", "").lower():
                        print("\nRate limited! Stopping...")
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                # skipped files are silent

    except KeyboardInterrupt:
        print("\n\nInterrupted! Progress saved.")

    print("\n" + "=" * 60)
    print(f"Total files: {stats['total']}")
    print(f"Downloaded: {stats['downloaded']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Failed: {stats['failed']}")
    print(f"Total completed: {len(progress.get('downloaded', []))}")


if __name__ == "__main__":
    main()
