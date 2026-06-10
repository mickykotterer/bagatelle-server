"""
upload_snapshots.py

The snapshot folders need to be re-packed into tar archives before uploading to Qdrant Cloud.
Run AFTER making sure the snapshot folders are fully downloaded from OneDrive
(right-click -> Always keep on this device).

Usage:
    .\.venv\Scripts\python.exe upload_snapshots.py
"""

import tarfile
import os
import requests
from dotenv import load_dotenv

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

if not QDRANT_URL or not QDRANT_API_KEY:
    raise RuntimeError("QDRANT_URL or QDRANT_API_KEY not found in .env file.")

SNAPSHOTS = [
    {
        "folder": "bagatelle_image_CLIP-L14-6019019360094818-2026-04-14-15-12-06.snapshot",
        "collection": "bagatelle_image_CLIP-L14",
    },
    {
        "folder": "bagatelle_text_CLIP-L14-6019019360094818-2026-04-14-15-12-21.snapshot",
        "collection": "bagatelle_text_CLIP-L14",
    },
]


def check_folder_has_data(folder):
    """Verify the snapshot folder has real content, not just OneDrive stubs."""
    shard_folder = os.path.join(folder, "0")
    if not os.path.exists(shard_folder):
        print(f"  ❌ No shard folder '0' found inside {folder}")
        return False

    files_in_shard = []
    for root, dirs, files in os.walk(shard_folder):
        files_in_shard.extend(files)

    if not files_in_shard:
        print(f"  ❌ Shard folder '0' is empty - OneDrive may not have downloaded it yet.")
        print(f"     Right-click the folder in File Explorer -> 'Always keep on this device'")
        return False

    total_size = sum(
        os.path.getsize(os.path.join(root, f))
        for root, dirs, files in os.walk(shard_folder)
        for f in files
    )
    print(f"  Shard data: {len(files_in_shard)} files, {total_size / (1024*1024):.1f} MB")
    return True


def pack_folder_to_tar(folder, tar_path):
    print(f"  Packing {folder} -> {tar_path} ...")
    with tarfile.open(tar_path, "w", dereference=True) as tar:
        tar.add(folder, arcname=os.path.basename(folder))
    size_mb = os.path.getsize(tar_path) / (1024 * 1024)
    print(f"  Packed: {size_mb:.1f} MB")


def upload_snapshot_file(tar_path, collection):
    url = f"{QDRANT_URL}/collections/{collection}/snapshots/upload"
    headers = {"api-key": QDRANT_API_KEY}
    print(f"  Uploading to Qdrant Cloud collection '{collection}' ...")

    with open(tar_path, "rb") as f:
        response = requests.post(
            url,
            headers=headers,
            files={"snapshot": (os.path.basename(tar_path), f, "application/octet-stream")},
            params={"priority": "snapshot"},
            timeout=600,
        )

    if response.ok:
        print(f"  ✅ Upload successful: {response.status_code}")
        return True
    else:
        print(f"  ❌ Upload failed: {response.status_code}")
        print(f"  Response: {response.text[:500]}")
        return False


if __name__ == "__main__":
    print("=== Qdrant Snapshot Upload ===\n")

    for snap in SNAPSHOTS:
        folder = snap["folder"]
        collection = snap["collection"]
        tar_path = folder + ".tar"

        print(f"-> Processing '{collection}'")

        if not os.path.isdir(folder):
            print(f"  ❌ Folder not found: {folder}")
            print()
            continue

        if not check_folder_has_data(folder):
            print()
            continue

        pack_folder_to_tar(folder, tar_path)
        upload_snapshot_file(tar_path, collection)

        if os.path.exists(tar_path):
            os.remove(tar_path)
            print(f"  Cleaned up {tar_path}")

        print()

    print("Done. Check your Qdrant Cloud dashboard to verify both collections exist.")
