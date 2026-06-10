import os
import csv
from PIL import Image
from sentence_transformers import SentenceTransformer
from qdrant_client.http.models import PointStruct
from api.qdrant_remote_client import get_remote_client

# ---------------- CONFIG ----------------
DATA_FILE = "data/artwork_names_filtered.csv"
IMAGES_DIR = "../static/data/images"
IMAGE_COLLECTION = "bagatelle_image_CLIP-L14"
TOP_K = 3
BATCH_SIZE = 50

data = []
with open(DATA_FILE, "r", encoding="utf8") as f:
    reader = csv.reader(f, delimiter=",")
    for row in reader:
        if not row or all(cell.strip() == "" for cell in row):
            continue
        print(row)
        filename = row[0].strip()
        title = row[1].strip()
        data.append({
            "filename": filename,
            "title": title
        })

client = get_remote_client()

print("Loading CLIP model...")
clip_model = SentenceTransformer("CLIP-ViT-L-14")

def embed_image(image):
    return clip_model.encode([image], normalize_embeddings=True)[0]

client.recreate_collection(
    collection_name=IMAGE_COLLECTION,
    vectors_config={"image_vector": {"size": 768, "distance": "Cosine"}},
)
print("Image collection created.")

# text_points = []
image_points = []
point_id = 0

count = 0
for item in data:
    count += 1
    # if count < 5:
    #     continue
    title = item.get("title", "")
    image_file = item.get("filename", "")
    image_path = os.path.join(IMAGES_DIR, image_file)

    # Embed image
    try:
        image = Image.open(image_path).convert("RGB")
        image_emb = embed_image(image)
    except Exception as e:
        print(f"Warning: failed to open {image_path}: {e}")
        continue  # skip this item if image fails

    # Add image point
    image_points.append(PointStruct(
        id=point_id,
        vector={"image_vector": image_emb},
        payload={"image_path": image_path, "title": title}
    ))
    point_id += 1

    # Batch insert if batch size reached
    if len(image_points) >= BATCH_SIZE:
        client.upsert(collection_name=IMAGE_COLLECTION, points=image_points)
        print(f"Inserted batch of {len(image_points)} image points")
        image_points = []

    print(count, image_file)

if image_points:
    client.upsert(collection_name=IMAGE_COLLECTION, points=image_points)
    print(f"Inserted final batch of {len(image_points)} image points")

print("All points inserted successfully.")
