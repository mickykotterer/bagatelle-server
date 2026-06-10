import os
import csv
from typing import List, Dict
from sentence_transformers import SentenceTransformer
from qdrant_client.http.models import PointStruct
from api.qdrant_remote_client import get_remote_client

# ---------------- CONFIG ----------------
DATA_FILE = "data/artwork_names_filtered.csv"  # filename,title
DESCRIPTION_FILE = "data/image_descriptions.csv"  # file_name,description (may be multiline)
IMAGES_DIR = "../static/data/images"
DESCRIPTION_COLLECTION = "bagatelle_description_CLIP-L14"
BATCH_SIZE = 50

# ---------------- LOAD TITLES ----------------
# Build a map from filename -> title for payload enrichment
filename_to_title: Dict[str, str] = {}
with open(DATA_FILE, "r", encoding="utf8", newline="") as f:
    reader = csv.reader(f)
    for row in reader:
        if not row or all((cell or "").strip() == "" for cell in row):
            continue
        filename = (row[0] or "").strip()
        title = (row[1] or "").strip() if len(row) > 1 else ""
        if filename:
            filename_to_title[filename] = title

# ---------------- LOAD DESCRIPTIONS ----------------
# Expecting CSV with headers: file_name, description. Descriptions can be quoted and multiline.
descriptions: List[Dict[str, str]] = []
with open(DESCRIPTION_FILE, "r", encoding="utf8", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if not row:
            continue
        file_name = (row.get("file_name") or "").strip()
        description = (row.get("description") or "").strip()
        if file_name and description:
            descriptions.append({"file_name": file_name, "description": description})

client = get_remote_client()

# ---------------- MODEL ----------------
print("Loading CLIP model...")
clip_model = SentenceTransformer("CLIP-ViT-L-14")

def embed_text(texts: List[str]):
    return clip_model.encode(texts, normalize_embeddings=True)

# ---------------- QDRANT COLLECTION ----------------
client.recreate_collection(
    collection_name=DESCRIPTION_COLLECTION,
    vectors_config={"text_vector": {"size": 768, "distance": "Cosine"}},
)
print("Description collection ready.")

# ---------------- UPSERT VECTORS ----------------
points_batch: List[PointStruct] = []
point_id = 0

# Process in batches for efficient encoding
for i in range(0, len(descriptions), BATCH_SIZE):
    batch = descriptions[i:i + BATCH_SIZE]
    texts = [item["description"] for item in batch]
    embs = embed_text(texts)

    for item, emb in zip(batch, embs):
        image_filename = item["file_name"]
        image_path = os.path.join(IMAGES_DIR, image_filename)
        title = filename_to_title.get(image_filename, "")
        payload = {
            "image_filename": image_filename,
            "image_path": image_path,
            "title": title,
            "description": item["description"],
        }
        points_batch.append(PointStruct(
            id=point_id,
            vector={"text_vector": emb},
            payload=payload
        ))
        point_id += 1

    client.upsert(collection_name=DESCRIPTION_COLLECTION, points=points_batch)
    print(f"Inserted batch of {len(points_batch)} description points (up to item {i + len(batch)})")
    points_batch = []

print("All description vectors inserted successfully.")
