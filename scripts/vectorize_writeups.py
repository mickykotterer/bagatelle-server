import os
import csv
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
from qdrant_client.http.models import PointStruct
from api.qdrant_remote_client import get_remote_client

# ---------------- CONFIG ----------------
HTML_CSV = os.path.join("..", "static", "data", "file_list_html.csv")
HTML_DIR = os.path.join("..", "static", "data", "html_gen_claude-sonnet-4")
IMAGES_DIR = os.path.join("..", "static", "data", "images")
TEXT_COLLECTION = "bagatelle_text_CLIP-L14"
BATCH_SIZE = 50

# ---------------- LOAD DATA ----------------
# file_list_html.csv has columns: Filename, Classification, html
mappings = []
with open(HTML_CSV, "r", encoding="utf8") as f:
    reader = csv.reader(f, delimiter=",")
    header = next(reader, None)
    for row in reader:
        if not row or all((c or "").strip() == "" for c in row):
            continue
        image_filename = (row[0] or "").strip()
        classification = (row[1] or "").strip() if len(row) > 1 else ""
        html_filename = (row[2] or "").strip() if len(row) > 2 else ""
        if image_filename and html_filename:
            mappings.append({
                "image_filename": image_filename,
                "classification": classification,
                "html_filename": html_filename,
            })

client = get_remote_client()

# ---------------- MODELS ----------------
print("Loading CLIP model...")
clip_model = SentenceTransformer("CLIP-ViT-L-14")

def embed_text(texts):
    return clip_model.encode(texts, normalize_embeddings=True)

# ---------------- CREATE/ENSURE COLLECTION ----------------
# Recreate the collection (note: this will clear existing data). If you prefer to keep data, replace with create_collection if not exists.
client.recreate_collection(
    collection_name=TEXT_COLLECTION,
    vectors_config={"text_vector": {"size": 768, "distance": "Cosine"}},
)
print("Text collection ready.")

text_points = []
point_id = 0

letters = ["a","b","c","d","e","f","g","h","i","j"]

def extract_sections_from_html(html_path: str):
    sections = []
    try:
        with open(html_path, "r", encoding="utf8") as f:
            soup = BeautifulSoup(f, "html.parser")
    except Exception as e:
        print(f"Failed to open/parse HTML {html_path}: {e}")
        return sections

    # Title (optional)
    h1 = soup.find("h1")
    page_title = h1.get_text(strip=True) if h1 else ""

    # Find all h2 and gather content until next h2
    for idx, h2 in enumerate(soup.find_all("h2")):
        section_title = h2.get_text(strip=True)
        # Collect sibling nodes until next h2
        texts = []
        for sib in h2.find_all_next():
            if sib.name == "h2":
                break
            # only consider elements that are within the same parent flow before next h2
            # stop if we reached another h2 which break above
            if sib.name in ("p", "ul", "ol", "li"):
                texts.append(sib.get_text(" ", strip=True))
            # Stop when we leave the content div if present
            if getattr(sib, "name", None) == "div" and "content" in sib.get("class", []):
                # continue inside content
                pass
        section_text = "\n".join([t for t in texts if t])
        sections.append({
            "key": letters[idx] if idx < len(letters) else "",
            "title": section_title,
            "text": section_text,
            "page_title": page_title,
        })
    return sections

count = 0
for m in mappings:
    count += 1
    image_filename = m["image_filename"]
    html_filename = m["html_filename"]
    classification = m.get("classification", "")

    image_path = os.path.join(IMAGES_DIR, image_filename)
    html_path = os.path.join(HTML_DIR, html_filename)

    sections = extract_sections_from_html(html_path)
    if not sections:
        print(f"No sections found for {html_filename}")
        continue

    # Create one vector per section
    section_texts = [s.get("text", "") for s in sections]
    embs = embed_text(section_texts)

    for s, emb in zip(sections, embs):
        payload = {
            "image_filename": image_filename,
            "image_path": image_path,
            "html_filename": html_filename,
            "html_path": html_path,
            "classification": classification,
            "section_key": s.get("key", ""),
            "section_title": s.get("title", ""),
            "section_text": s.get("text", ""),
            "page_title": s.get("page_title", ""),
        }
        text_points.append(PointStruct(
            id=point_id,
            vector={"text_vector": emb},
            payload=payload
        ))
        point_id += 1

    if len(text_points) >= BATCH_SIZE:
        client.upsert(collection_name=TEXT_COLLECTION, points=text_points)
        print(f"Inserted batch of {len(text_points)} text points (up to row {count})")
        text_points = []

    if count % 50 == 0:
        print(f"Processed {count} HTML mappings")

# Final flush
if text_points:
    client.upsert(collection_name=TEXT_COLLECTION, points=text_points)
    print(f"Inserted final batch of {len(text_points)} text points")

print("All section vectors inserted successfully.")
