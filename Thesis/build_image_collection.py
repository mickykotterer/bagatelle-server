"""
build_image_collection.py

Builds a Qdrant image collection using CLIP-L14 embeddings computed
directly from the artwork images in static/data/images/.

This replaces the need to upload the supervisor's snapshot.

Usage:
    .\.venv\Scripts\python.exe build_image_collection.py
"""

import os
import csv
import re
from dotenv import load_dotenv
from PIL import Image
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

load_dotenv()

# --- CONFIG ---
IMAGE_FOLDER = os.path.join("static", "data", "images")
COLLECTION_NAME = "bagatelle_image_CLIP-L14"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".jfif", ".avif"}

# CLIP-L14 produces 768-dim vectors (same as the supervisor's collection)
model = SentenceTransformer("clip-ViT-L-14")

client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)


def normalize_filename(name):
    return os.path.basename(name).strip().lower()


def load_category_map():
    csv_path = os.path.join("static", "data", "file_list_html.csv")
    category_map = {}
    if not os.path.exists(csv_path):
        print(f"No category CSV found at {csv_path}")
        return category_map
    with open(csv_path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            filename = row[0].strip()
            category = row[1].strip()
            if filename and category:
                category_map[normalize_filename(filename)] = category
    print(f"Loaded {len(category_map)} categories")
    return category_map


def clean_filename_title(filename):
    name = os.path.splitext(os.path.basename(filename))[0]
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    name = name.replace("_", " ").replace("-", " ")
    name = re.sub(r"\b\d{2,5}x\d{2,5}\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# --- SETUP ---
print(f"Creating collection '{COLLECTION_NAME}' (768-dim CLIP-L14 image vectors)...")

client.recreate_collection(
    collection_name=COLLECTION_NAME,
    vectors_config={
        "image_vector": VectorParams(size=768, distance=Distance.COSINE)
    }
)

category_map = load_category_map()

# --- PROCESS IMAGES ---
points = []
skipped = 0

image_files = [
    f for f in os.listdir(IMAGE_FOLDER)
    if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS
]

print(f"Found {len(image_files)} images to process\n")

for i, filename in enumerate(image_files):
    image_path = os.path.join(IMAGE_FOLDER, filename).replace("\\", "/")

    try:
        img = Image.open(image_path).convert("RGB")
        embedding = model.encode(img).tolist()
    except Exception as e:
        print(f"⚠️  Skipping {filename}: {e}")
        skipped += 1
        continue

    category = category_map.get(normalize_filename(filename), "")
    title = clean_filename_title(filename)

    points.append({
        "id": i,
        "vector": {
            "image_vector": embedding
        },
        "payload": {
            "image_path": image_path,
            "title": title,
            "category": category,
        }
    })

    if (i + 1) % 50 == 0:
        print(f"Processed {i + 1}/{len(image_files)}")

# --- UPLOAD IN BATCHES ---
print(f"\nUploading {len(points)} points to Qdrant (skipped {skipped})...")

BATCH_SIZE = 50
for start in range(0, len(points), BATCH_SIZE):
    batch = points[start:start + BATCH_SIZE]
    client.upsert(collection_name=COLLECTION_NAME, points=batch)
    print(f"  Uploaded {min(start + BATCH_SIZE, len(points))}/{len(points)}")

print(f"\nDone! Collection '{COLLECTION_NAME}' is ready.")
print("Next: run create_qdrant_indexes.py if you want image_path filtering on this collection.")
