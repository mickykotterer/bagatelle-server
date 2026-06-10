from sentence_transformers import SentenceTransformer
from bs4 import BeautifulSoup
from qdrant_client import QdrantClient
from dotenv import load_dotenv
import os
import csv
import re
from qdrant_client.models import VectorParams, Distance

def normalize_filename(name):
    return os.path.basename(name).strip().lower()


def clean_title(title):
    if not title:
        return ""

    title = title.strip()
    title = re.sub(r"\s+", " ", title)

    # Remove common generated suffixes/prefixes if they appear
    title = title.replace("Art Historical and Biomedical Analysis", "").strip()
    title = title.replace("Historical and Biomedical Analysis", "").strip()
    title = title.replace("Art and Medicine Analysis", "").strip()
    title = title.replace("Art Historical and Medical Analysis", "").strip()
    title = title.replace("Art and Medical Analysis", "").strip()

    return title


def is_bad_title(title):
    if not title:
        return True

    lower = title.lower().strip()

    bad_phrases = [
        "art historical and biomedical analysis",
        "historical and biomedical analysis",
        "art and medicine analysis",
        "art and medical analysis",
        "art historical and medical analysis",
        "artist/ group/tribe",
        "artist / group / tribe",
        "historical and socio-cultural context",
        "symbolism and/or iconography",
        "symbolism and or iconography",
        "stylistic significance",
        "social / cultural inequities",
        "description of disease",
        "pathology signs",
        "treatment",
        "references and citations",
        "references",
        "citations",
    ]

    if any(phrase == lower for phrase in bad_phrases):
        return True

    if any(phrase in lower for phrase in bad_phrases) and len(title) < 80:
        return True

    # Skip citation-looking titles
    if re.match(r"^\d+\.", lower):
        return True

    if "doi" in lower or "http" in lower or "university press" in lower:
        return True

    return False


def clean_filename_title(filename):
    name = os.path.splitext(os.path.basename(filename))[0]

    # Insert spaces between camel-case-ish words
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)

    # Replace separators
    name = name.replace("_", " ").replace("-", " ")

    # Remove image-size fragments like 980x1321
    name = re.sub(r"\b\d{2,5}x\d{2,5}\b", "", name, flags=re.IGNORECASE)

    # Remove hash-like fragments
    name = re.sub(r"\b[a-f0-9]{16,}\b", "", name, flags=re.IGNORECASE)

    name = re.sub(r"\s+", " ", name).strip()

    return name


def load_title_map():
    """
    Try to load human-readable artwork titles/captions from existing CSV files.
    Expected rough structure:
    column 0 = filename
    column 1 = title/caption/classification-ish text
    """
    possible_csvs = [
        os.path.join("static", "data", "artwork_names_filtered.csv"),
        os.path.join("data", "artwork_names_filtered.csv"),
    ]

    title_map = {}

    for csv_path in possible_csvs:
        if not os.path.exists(csv_path):
            continue

        print(f"Loading title metadata from {csv_path}")

        with open(csv_path, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)

            for row in reader:
                if not row or len(row) < 2:
                    continue

                filename = row[0].strip()
                title = row[1].strip()

                if not filename or not title:
                    continue

                if is_bad_title(title):
                    continue

                title_map[normalize_filename(filename)] = clean_title(title)

    print(f"Loaded {len(title_map)} metadata titles")
    return title_map

def load_category_map():
    csv_path = os.path.join("static", "data", "file_list_html.csv")
    category_map = {}

    if not os.path.exists(csv_path):
        print(f"No category CSV found at {csv_path}")
        return category_map

    with open(csv_path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)

        for row in reader:
            if len(row) < 2:
                continue

            filename = row[0].strip()
            category = row[1].strip()

            if filename and category:
                category_map[normalize_filename(filename)] = category

    print(f"Loaded {len(category_map)} categories")
    return category_map

def guess_title_from_text_or_filename(text, filename):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines[:20]:
        line = clean_title(line)

        if is_bad_title(line):
            continue

        if len(line) > 100:
            continue

        return line

    return clean_filename_title(filename)


def choose_display_title(page_title, text, image_path, html_filename, title_map):
    image_filename = os.path.basename(image_path)

    # 1. Best source: metadata CSV
    csv_title = title_map.get(normalize_filename(image_filename))
    if csv_title and not is_bad_title(csv_title):
        return csv_title

    # 2. HTML h1/title if not generic
    page_title = clean_title(page_title)
    if page_title and not is_bad_title(page_title):
        return page_title

    # 3. Guess from LLM text
    guessed = guess_title_from_text_or_filename(text, html_filename)
    if guessed and not is_bad_title(guessed):
        return guessed

    # 4. Fallback: cleaned filename
    return clean_filename_title(image_filename)


def normalize_name(name):
    """
    Normalize filenames so small differences in punctuation/capitalization
    do not prevent matching.
    """
    return "".join(ch.lower() for ch in name if ch.isalnum())

def find_closest_image_filenames(filename, max_results=5):
    image_folder = os.path.join("static", "data", "images")
    html_stem = os.path.splitext(filename)[0]
    normalized_html_stem = normalize_name(html_stem)

    if not os.path.exists(image_folder):
        return []

    candidates = []

    for image_filename in os.listdir(image_folder):
        image_stem, image_ext = os.path.splitext(image_filename)

        if image_ext.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".jfif", ".avif"}:
            continue

        normalized_image_stem = normalize_name(image_stem)

        # Simple overlap score: how much of the shorter name overlaps
        common_chars = set(normalized_html_stem) & set(normalized_image_stem)
        score = len(common_chars)

        if (
            normalized_html_stem[:20] in normalized_image_stem
            or normalized_image_stem[:20] in normalized_html_stem
        ):
            score += 50

        candidates.append((score, image_filename))

    candidates.sort(reverse=True)
    return [name for score, name in candidates[:max_results]]

IMAGE_OVERRIDES = {
    "AchillesBandagingPatroklos.html": "AchillesBandagingPatrocluscupSosiasPainterPhotographbyMariaDanielscourtesyoftheStaatlicheMuseenzuBerlin.jpg",
    "typeofman.html": "IllustrationfromTypesofMankind1854whoseauthorsJosiahClarkNottandGeorgeRobinsGliddon.jpg",
}

def find_image_path_for_html(filename):
    image_folder = os.path.join("static", "data", "images")

    # 0. Manual fixes for HTML files whose image filename differs too much
    if filename in IMAGE_OVERRIDES:
        candidate = os.path.join(image_folder, IMAGE_OVERRIDES[filename])

        if os.path.exists(candidate):
            return candidate.replace("\\", "/")

        print(f"⚠️ Override image not found for {filename}: {candidate}")

    html_stem = os.path.splitext(filename)[0]
    normalized_html_stem = normalize_name(html_stem)

    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".jfif", ".avif"}

    # 1. First try exact stem match with common extensions
    for ext in allowed_extensions:
        candidate = os.path.join(image_folder, html_stem + ext)
        if os.path.exists(candidate):
            return candidate.replace("\\", "/")

    # 2. Then try normalized matching against all image files
    for image_filename in os.listdir(image_folder):
        image_stem, image_ext = os.path.splitext(image_filename)

        if image_ext.lower() not in allowed_extensions:
            continue

        if normalize_name(image_stem) == normalized_html_stem:
            return os.path.join(image_folder, image_filename).replace("\\", "/")

    return None

load_dotenv()

# --- CONFIG via command-line argument ---
# Usage:
#   python build_text_collection.py --model gpt4o    → bagatelle_text_gpt4o
#   python build_text_collection.py --model claude   → bagatelle_text_claude
#   python build_text_collection.py --model gpt5     → bagatelle_text_gpt5
#
# Omit --model to rebuild the legacy collection (bagatelle_text_CLIP-L14) from html_gpt-4o.

import argparse as _argparse

_MODELS = {
    "gpt4o":  ("static/data/html_gpt-4o",          "bagatelle_text_gpt4o"),
    "claude": ("static/data/html_claude-sonnet-4",  "bagatelle_text_claude"),
    "gpt5":   ("static/data/html_gpt-5",            "bagatelle_text_gpt5"),
    # Legacy default — keeps the existing collection name intact
    "legacy": ("static/data/html_gpt-4o",           "bagatelle_text_CLIP-L14"),
}

_parser = _argparse.ArgumentParser(description="Build a Bagatelle text collection")
_parser.add_argument("--model", choices=list(_MODELS.keys()), default="legacy",
                     help="Which LLM description set to embed")
_args, _ = _parser.parse_known_args()

HTML_FOLDER, COLLECTION_NAME = _MODELS[_args.model]
print(f"Building collection '{COLLECTION_NAME}' from '{HTML_FOLDER}' ...")

# --- INIT ---
model = SentenceTransformer("all-MiniLM-L6-v2") #("clip-ViT-L-14")

client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)

title_map = load_title_map()
category_map = load_category_map()

# --- CREATE COLLECTION ---
client.recreate_collection(
    collection_name=COLLECTION_NAME,
    vectors_config={
        "text_vector": VectorParams(size=384, distance=Distance.COSINE)
    }
)
#client.recreate_collection(
#    collection_name=COLLECTION_NAME,
#    vectors_config={
#        "size": 768,
#        "distance": "Cosine"
#    }
#)

points = []

# --- LOOP FILES ---
for i, filename in enumerate(os.listdir(HTML_FOLDER)):
    if not filename.endswith(".html"):
        continue

    path = os.path.join(HTML_FOLDER, filename)

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f, "html.parser")

        for tag in soup(["script", "style"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)

        h1 = soup.find("h1")
        page_title = h1.get_text(" ", strip=True) if h1 else ""

        if not page_title:
            title_tag = soup.find("title")
            page_title = title_tag.get_text(" ", strip=True) if title_tag else ""

    # Create embedding
    embedding = model.encode(text).tolist()

    #if i == 0:
    #    print(text[:1000])

    # Find matching image
    image_path = find_image_path_for_html(filename)

    if image_path is None:
        print(f"\n⚠️ No image found for HTML file: {filename}")
        print("Closest image filename candidates:")
        for candidate in find_closest_image_filenames(filename):
            print(f"   - {candidate}")
        continue

    # Choose best display title
    display_title = choose_display_title(
        page_title=page_title,
        text=text,
        image_path=image_path,
        html_filename=filename,
        title_map=title_map
    )

    image_filename = os.path.basename(image_path)
    category = category_map.get(normalize_filename(image_filename), "")

    points.append({
        "id": i,
        "vector": {
            "text_vector": embedding
        },
        "payload": {
            "image_path": image_path,
            "title": display_title,
            "category": category,
            "section_text": text
        }
    })

    if i % 50 == 0:
        print(f"Processed {i}")

# --- UPLOAD in batches ---
BATCH_SIZE = 50
print(f"\nUploading {len(points)} points in batches of {BATCH_SIZE}...")
for start in range(0, len(points), BATCH_SIZE):
    batch = points[start:start + BATCH_SIZE]
    client.upsert(collection_name=COLLECTION_NAME, points=batch)
    print(f"  Uploaded {min(start + BATCH_SIZE, len(points))}/{len(points)}")

print(f"\nDone! Collection '{COLLECTION_NAME}' is ready.")
print("Next: run create_qdrant_indexes.py to create image_path index on the new collection.")