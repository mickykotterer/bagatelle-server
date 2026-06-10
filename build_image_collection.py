r"""
build_image_collection.py

Builds a Qdrant image collection from artwork images using a choice of embedding model.

Usage:
    .\.venv\Scripts\python.exe build_image_collection.py --model clip      # CLIP-L14 (default, 768-dim)
    .\.venv\Scripts\python.exe build_image_collection.py --model openclip  # OpenCLIP ViT-L-14 (768-dim)
    .\.venv\Scripts\python.exe build_image_collection.py --model siglip2   # SigLIP 2 so400m (1152-dim)

Requirements:
    clip      — sentence-transformers (already installed)
    openclip  — pip install open-clip-torch
    siglip2   — transformers + torch (already installed)
"""

import os
import csv
import re
import argparse
from dotenv import load_dotenv
from PIL import Image
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

load_dotenv()

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODEL_CONFIGS = {
    "clip": {
        "collection": "bagatelle_image_CLIP-L14",
        "dim":        768,
        "description": "CLIP ViT-L/14 (sentence-transformers)",
    },
    "openclip": {
        "collection": "bagatelle_image_openclip",
        "dim":        768,
        "description": "OpenCLIP ViT-L-14 (open-clip-torch)",
    },
    "siglip2": {
        "collection": "bagatelle_image_siglip2",
        "dim":        1152,
        "description": "SigLIP 2 so400m-patch14-384 (transformers)",
    },
}

parser = argparse.ArgumentParser(description="Build a Bagatelle image collection")
parser.add_argument(
    "--model",
    choices=list(MODEL_CONFIGS.keys()),
    default="clip",
    help="Embedding model to use",
)
args, _ = parser.parse_known_args()

cfg = MODEL_CONFIGS[args.model]
COLLECTION_NAME = cfg["collection"]
VECTOR_DIM      = cfg["dim"]
IMAGE_FOLDER    = os.path.join("static", "data", "images")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".jfif", ".avif"}

print(f"Model:      {cfg['description']}")
print(f"Collection: {COLLECTION_NAME}  ({VECTOR_DIM}-dim)")
print()

# ---------------------------------------------------------------------------
# Load the chosen embedding model
# ---------------------------------------------------------------------------

def load_model(model_key):
    if model_key == "clip":
        from sentence_transformers import SentenceTransformer
        print("Loading CLIP ViT-L/14 via sentence-transformers...")
        m = SentenceTransformer("clip-ViT-L-14")

        def encode_image(img: Image.Image):
            return m.encode(img).tolist()

        def encode_text(text: str):
            return m.encode(text).tolist()

        return encode_image, encode_text

    elif model_key == "openclip":
        try:
            import open_clip
        except ImportError:
            raise ImportError(
                "open-clip-torch is not installed.\n"
                "Run:  .venv\\Scripts\\pip install open-clip-torch"
            )
        import torch
        print("Loading OpenCLIP ViT-L-14...")
        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-L-14", pretrained="openai"
        )
        tokenizer = open_clip.get_tokenizer("ViT-L-14")
        model.eval()

        def encode_image(img: Image.Image):
            tensor = preprocess(img).unsqueeze(0)
            with torch.no_grad():
                feat = model.encode_image(tensor)
                feat = feat / feat.norm(dim=-1, keepdim=True)
            return feat.squeeze(0).tolist()

        def encode_text(text: str):
            tokens = tokenizer([text])
            with torch.no_grad():
                feat = model.encode_text(tokens)
                feat = feat / feat.norm(dim=-1, keepdim=True)
            return feat.squeeze(0).tolist()

        return encode_image, encode_text

    elif model_key == "siglip2":
        import torch
        from transformers import AutoProcessor, AutoModel
        MODEL_ID = "google/siglip2-so400m-patch14-384"
        print(f"Loading SigLIP 2 ({MODEL_ID})...")
        print("(First run will download ~1.5 GB — cached afterwards)")
        processor = AutoProcessor.from_pretrained(MODEL_ID)
        model = AutoModel.from_pretrained(MODEL_ID)
        model.eval()

        def encode_image(img: Image.Image):
            inputs = processor(images=img, return_tensors="pt")
            with torch.no_grad():
                # Use vision_model directly — get_image_features may return
                # a BaseModelOutputWithPooling object on some transformers versions
                out = model.vision_model(pixel_values=inputs["pixel_values"])
                feat = out.pooler_output  # shape (1, hidden_dim)
                feat = feat / feat.norm(dim=-1, keepdim=True)
            return feat.squeeze(0).tolist()

        def encode_text(text: str):
            inputs = processor(text=[text], return_tensors="pt", padding=True)
            with torch.no_grad():
                out = model.text_model(
                    input_ids=inputs["input_ids"],
                    attention_mask=inputs.get("attention_mask"),
                )
                feat = out.pooler_output
                feat = feat / feat.norm(dim=-1, keepdim=True)
            return feat.squeeze(0).tolist()

        return encode_image, encode_text

    raise ValueError(f"Unknown model: {model_key}")


encode_image, encode_text = load_model(args.model)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
            filename, category = row[0].strip(), row[1].strip()
            if filename and category:
                category_map[normalize_filename(filename)] = category
    print(f"Loaded {len(category_map)} categories")
    return category_map


def clean_filename_title(filename):
    name = os.path.splitext(os.path.basename(filename))[0]
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    name = name.replace("_", " ").replace("-", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ---------------------------------------------------------------------------
# Connect to Qdrant and (re)create collection
# ---------------------------------------------------------------------------

client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)

print(f"\nCreating collection '{COLLECTION_NAME}' ({VECTOR_DIM}-dim, cosine)...")
client.recreate_collection(
    collection_name=COLLECTION_NAME,
    vectors_config={
        "image_vector": VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
    }
)

category_map = load_category_map()

# ---------------------------------------------------------------------------
# Process images
# ---------------------------------------------------------------------------

image_files = [
    f for f in os.listdir(IMAGE_FOLDER)
    if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS
]
print(f"Found {len(image_files)} images\n")

points  = []
skipped = 0

for i, filename in enumerate(image_files):
    image_path = os.path.join(IMAGE_FOLDER, filename).replace("\\", "/")

    try:
        img = Image.open(image_path).convert("RGB")
        embedding = encode_image(img)
    except Exception as e:
        print(f"  Skipping {filename}: {e}")
        skipped += 1
        continue

    points.append({
        "id": i,
        "vector": {"image_vector": embedding},
        "payload": {
            "image_path": image_path,
            "title":      clean_filename_title(filename),
            "category":   category_map.get(normalize_filename(filename), ""),
        },
    })

    if (i + 1) % 50 == 0:
        print(f"  Embedded {i + 1}/{len(image_files)}")

# ---------------------------------------------------------------------------
# Upload in batches
# ---------------------------------------------------------------------------

print(f"\nUploading {len(points)} points (skipped {skipped})...")
BATCH_SIZE = 50
for start in range(0, len(points), BATCH_SIZE):
    batch = points[start:start + BATCH_SIZE]
    client.upsert(collection_name=COLLECTION_NAME, points=batch)
    print(f"  Uploaded {min(start + BATCH_SIZE, len(points))}/{len(points)}")

print(f"\nDone! Collection '{COLLECTION_NAME}' is ready.")
print("Next: run create_qdrant_indexes.py to create the image_path index.")
