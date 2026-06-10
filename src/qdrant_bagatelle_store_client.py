import re
import numpy as np
from api.qdrant_remote_client import get_remote_client
from qdrant_client.models import Filter, FieldCondition, MatchValue

# Use fastembed (ONNX-based, ~50MB) instead of sentence-transformers+torch (~350MB).
# Produces identical 384-dim MiniLM vectors, compatible with existing Qdrant collections.
try:
    from fastembed import TextEmbedding as _FastEmbed
    _USE_FASTEMBED = True
except ImportError:
    # Fallback to sentence-transformers if fastembed not installed (local dev)
    from sentence_transformers import SentenceTransformer as _SentenceTransformer
    _USE_FASTEMBED = False

# Collections
TEXT_CLIP_COLLECTION  = "bagatelle_text_CLIP-L14"   # default (GPT-4o descriptions, MiniLM)
IMAGE_CLIP_COLLECTION = "bagatelle_image_CLIP-L14"  # CLIP-L14 image embeddings (768-dim)

# Description source → Qdrant text collection
DESCRIPTION_COLLECTIONS = {
    "gpt4o":  "bagatelle_text_gpt4o",
    "claude": "bagatelle_text_claude",
    "gpt5":   "bagatelle_text_gpt5",
    "legacy": TEXT_CLIP_COLLECTION,
}

# Image model → (Qdrant collection, vector_dim)
IMAGE_COLLECTIONS = {
    "clip":     ("bagatelle_image_CLIP-L14",  768),
    "openclip": ("bagatelle_image_openclip",  768),
    "siglip2":  ("bagatelle_image_siglip2",  1152),
}

def get_text_collection(description_source: str) -> str:
    """Return the Qdrant collection name for a given text description source key."""
    return DESCRIPTION_COLLECTIONS.get(description_source, TEXT_CLIP_COLLECTION)

def get_image_collection(image_model: str) -> str:
    """Return the Qdrant collection name for a given image embedding model key."""
    return IMAGE_COLLECTIONS.get(image_model, (IMAGE_CLIP_COLLECTION, 768))[0]

# Embedding models — lazy-loaded
_minilm_model = None
_clip_model = None

def _get_minilm_model():
    global _minilm_model
    if _minilm_model is None:
        if _USE_FASTEMBED:
            _minilm_model = _FastEmbed(model_name="sentence-transformers/all-MiniLM-L6-v2")
        else:
            _minilm_model = _SentenceTransformer("all-MiniLM-L6-v2")
    return _minilm_model

def _get_clip_model():
    global _clip_model
    if _clip_model is None:
        try:
            if _USE_FASTEMBED:
                raise RuntimeError("CLIP not available via fastembed on this deployment.")
            _clip_model = _SentenceTransformer("clip-ViT-L-14")
        except Exception as e:
            raise RuntimeError(
                f"CLIP model unavailable (expected on low-memory deployments). "
                f"Use text or combined mode instead. Original error: {e}"
            )
    return _clip_model

def embed_query_minilm(text):
    """384-dim MiniLM embedding — used for bagatelle_text_CLIP-L14."""
    model = _get_minilm_model()
    if _USE_FASTEMBED:
        return list(model.embed([text]))[0].tolist()
    return model.encode(text).tolist()

def embed_query_clip(text):
    """768-dim CLIP-L14 text embedding — used for bagatelle_image_CLIP-L14 text queries."""
    model = _get_clip_model()
    if _USE_FASTEMBED:
        raise RuntimeError("CLIP not available on this deployment.")
    return model.encode(text).tolist()

# Legacy alias
def embed_query(text):
    return embed_query_minilm(text)


# ---------------------------------------------------------------------------
# Title helper
# ---------------------------------------------------------------------------

def _clean_filename(name):
    """Convert a CamelCase or hash-prefixed filename to readable text."""
    # Remove leading 32-char hex hash
    name = re.sub(r'^[0-9a-f]{32}', '', name)
    # Remove trailing image-extension fragments baked into the name
    name = re.sub(r'(jpg|jpeg|png|webp|gif|avif|jfif)(.*?)$', r'\2', name, flags=re.IGNORECASE)
    # Remove page-number suffixes like pg201, pg32
    name = re.sub(r'pg\d+$', '', name, flags=re.IGNORECASE)
    # Insert spaces before capital letters in CamelCase
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    # Insert space before AND after a 4-digit year
    name = re.sub(r'([a-zA-Z])(\d{4})', r'\1 \2', name)
    name = re.sub(r'(\d{4})([a-zA-Z])', r'\1 \2', name)
    # Collapse runs of spaces/underscores
    name = re.sub(r'[\s_]+', ' ', name).strip()
    return name or "Unknown artwork"


def make_artwork_title(image_path, text):
    """
    Extract a readable title from the LLM-generated description text.
    Falls back to a cleaned version of the filename.
    """
    filename = image_path.split("/")[-1]
    fallback = _clean_filename(filename.rsplit(".", 1)[0])

    if not text:
        return fallback

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Phrases that identify generic template headers — skip these lines
    bad_phrases = [
        "art historical and biomedical analysis",
        "historical and biomedical analysis",
        "art historical analysis",
        "artwork and biomedical",
        "art and medicine",
        "art and science",
        "art and analysis",
        "art & medicine",
        "artist/ group/tribe",
        "artist / group / tribe",
        "artist/group/tribe",
        "historical and socio-cultural context",
        "socio-cultural context",
        "symbolism and/or iconography",
        "symbolism and or iconography",
        "symbolism and iconography",
        "stylistic significance",
        "elements of art",
        "principles of design",
        "social / cultural inequities",
        "social/cultural inequities",
        "description of disease",
        "pathology signs",
        "signifiers of illness",
        "references and citations",
        "further reading",
        "biomedical context",
    ]

    # Pass 1: try to extract a title embedded in a bad-phrase heading
    # e.g. 'Art Historical and Biomedical Analysis of "Raft of the Medusa"'
    #   → 'Raft of the Medusa'
    for line in lines[:5]:
        lower = line.lower()
        if any(phrase in lower for phrase in bad_phrases):
            # Look for  '... of "Title"'  or  '... of Title by Artist'
            m = re.search(
                r'\bof\s+[“‘"]?([A-Z][^"”’\n]{3,80}?)[”’"]?\s*$',
                line
            )
            if m:
                candidate = m.group(1).strip().strip('"')
                if 4 <= len(candidate) <= 80:
                    return candidate

    # Pass 2: find the first short, clean, non-generic line
    for line in lines[:20]:
        cleaned = line.strip()
        lower = cleaned.lower()

        # Skip generic template phrases
        if any(phrase in lower for phrase in bad_phrases):
            continue

        # Skip section markers like [a], [b], (a), 1., etc.
        if re.match(r'^[\[\(]?\s*[a-zA-Z0-9]\s*[\]\)][\.\s]', cleaned):
            continue

        # Skip lines that are too long (paragraphs) or too short
        if len(cleaned) > 100 or len(cleaned) < 4:
            continue

        # Skip lines that look like bare filenames (e.g. "foo.jpg")
        if re.search(r'\.\w{2,4}$', cleaned) and len(cleaned.split()) <= 3:
            continue

        return cleaned

    return fallback


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _get_point_by_image_path(client, collection_name, image_path, with_vectors=False):
    """Scroll to find the first point with matching image_path. Returns the point or None."""
    matches, _ = client.scroll(
        collection_name=collection_name,
        scroll_filter=Filter(
            must=[FieldCondition(key="image_path", match=MatchValue(value=image_path))]
        ),
        limit=1,
        with_payload=True,
        with_vectors=with_vectors
    )
    return matches[0] if matches else None


def _lookup_text_description(client, image_path, text_collection=None):
    """
    Return (section_text, title) from the text collection for an image_path.
    Used by image mode to enrich results with descriptions.
    """
    collection = text_collection or TEXT_CLIP_COLLECTION
    point = _get_point_by_image_path(client, collection, image_path)
    if point:
        text = point.payload.get("section_text", "")
        title = point.payload.get("title") or make_artwork_title(image_path, text)
        return text, title
    # Fallback to default collection if the selected one doesn't have this artwork
    if collection != TEXT_CLIP_COLLECTION:
        point = _get_point_by_image_path(client, TEXT_CLIP_COLLECTION, image_path)
        if point:
            text = point.payload.get("section_text", "")
            title = point.payload.get("title") or make_artwork_title(image_path, text)
            return text, title
    return "", make_artwork_title(image_path, "")


# ---------------------------------------------------------------------------
# Core: get_related_artworks — dispatches by mode
# ---------------------------------------------------------------------------

def get_related_artworks(image_path, top_k=3, exclude_paths=None, mode="text_clip",
                         text_weight=0.5, image_weight=0.5,
                         query=None, query_weight=0.4,
                         description_source="legacy", image_model="clip"):
    """
    Find artworks related to image_path using the selected graph mode.

    mode:
      "text_clip"      — semantic text similarity (CLIP-L14 text vectors)
      "image_clip"     — visual similarity (CLIP-L14 image vectors)
      "combined_clip"  — weighted combination of both
      "query_targeted" — text similarity steered by the original search query
    """
    text_collection  = get_text_collection(description_source)
    image_collection = get_image_collection(image_model)

    if mode == "image_clip":
        return _get_related_by_stored_vector(
            image_path=image_path,
            primary_collection=image_collection,
            vector_name="image_vector",
            top_k=top_k,
            exclude_paths=exclude_paths,
            fetch_descriptions=True,
            text_collection_override=text_collection,
        )
    elif mode == "combined_clip":
        return _get_related_combined(
            image_path=image_path,
            top_k=top_k,
            exclude_paths=exclude_paths,
            text_weight=text_weight,
            image_weight=image_weight,
            text_collection=text_collection,
            image_collection=image_collection,
        )
    elif mode == "query_targeted" and query:
        return _get_related_query_targeted(
            image_path=image_path,
            query=query,
            top_k=top_k,
            exclude_paths=exclude_paths,
            query_weight=query_weight,
            text_collection=text_collection,
        )
    else:
        # Default: text_clip (also fallback for query_targeted with no query)
        return _get_related_by_stored_vector(
            image_path=image_path,
            primary_collection=text_collection,
            vector_name="text_vector",
            top_k=top_k,
            exclude_paths=exclude_paths,
            fetch_descriptions=False,
        )


def _get_related_combined(image_path, top_k=3, exclude_paths=None,
                          text_weight=0.5, image_weight=0.5,
                          text_collection=None, image_collection=None):
    """
    Combined graph expansion: query text and image collections separately
    using each artwork's stored vector, then merge scores.

    text_weight + image_weight do not need to sum to 1 — they are applied
    independently so each modality contributes on its own scale.
    """
    client = get_remote_client()

    if exclude_paths is None:
        exclude_paths = []
    exclude_paths = set(exclude_paths)

    OVERFETCH = 60  # fetch more candidates so merging has enough to filter from

    # --- Retrieve stored vectors for the selected artwork ---
    _text_col  = text_collection  or TEXT_CLIP_COLLECTION
    _image_col = image_collection or IMAGE_CLIP_COLLECTION
    text_point = _get_point_by_image_path(
        client, _text_col, image_path, with_vectors=True
    )
    image_point = _get_point_by_image_path(
        client, _image_col, image_path, with_vectors=True
    )

    if not text_point and not image_point:
        print(f"[combined] No point found for {image_path} in either collection")
        return {
            "selected": {
                "image_path": image_path,
                "title": make_artwork_title(image_path, ""),
                "category": "",
                "text_preview": "",
                "text_full": "",
            },
            "related": [],
        }

    # --- Build selected artwork metadata ---
    selected_text = ""
    selected_title = make_artwork_title(image_path, "")
    selected_category = ""

    if text_point:
        selected_text = text_point.payload.get("section_text", "")
        selected_title = (
            text_point.payload.get("title")
            or make_artwork_title(image_path, selected_text)
        )
    if image_point:
        selected_category = image_point.payload.get("category", "")
        if not selected_title or selected_title == make_artwork_title(image_path, ""):
            selected_title = image_point.payload.get("title") or selected_title

    print(f"[combined] Selected: {selected_title}")

    # --- Query text collection ---
    candidate_scores = {}  # image_path -> merged score info

    if text_point:
        raw = text_point.vector
        text_vec = raw.get("text_vector") if isinstance(raw, dict) else raw
        if text_vec:
            resp = client.query_points(
                collection_name=_text_col,
                query=text_vec,
                using="text_vector",
                limit=OVERFETCH,
                with_payload=True,
                with_vectors=False,
            )
            for r in resp.points:
                path = r.payload.get("image_path")
                if not path or path == image_path:
                    continue
                if path not in candidate_scores:
                    candidate_scores[path] = {
                        "combined": 0.0, "text_score": 0.0, "image_score": 0.0,
                        "text_payload": None, "image_payload": None,
                    }
                candidate_scores[path]["combined"] += r.score * text_weight
                candidate_scores[path]["text_score"] = r.score
                candidate_scores[path]["text_payload"] = r.payload

    # --- Query image collection ---
    if image_point:
        raw = image_point.vector
        image_vec = raw.get("image_vector") if isinstance(raw, dict) else raw
        if image_vec:
            resp = client.query_points(
                collection_name=_image_col,
                query=image_vec,
                using="image_vector",
                limit=OVERFETCH,
                with_payload=True,
                with_vectors=False,
            )
            for r in resp.points:
                path = r.payload.get("image_path")
                if not path or path == image_path:
                    continue
                if path not in candidate_scores:
                    candidate_scores[path] = {
                        "combined": 0.0, "text_score": 0.0, "image_score": 0.0,
                        "text_payload": None, "image_payload": None,
                    }
                candidate_scores[path]["combined"] += r.score * image_weight
                candidate_scores[path]["image_score"] = r.score
                candidate_scores[path]["image_payload"] = r.payload

    # --- Sort and build results ---
    sorted_candidates = sorted(
        candidate_scores.items(), key=lambda x: x[1]["combined"], reverse=True
    )

    related = []
    seen = set()

    for path, info in sorted_candidates:
        if path in exclude_paths or path in seen:
            continue
        seen.add(path)

        # Get description and title
        tpay = info["text_payload"]
        ipay = info["image_payload"]

        candidate_text = tpay.get("section_text", "") if tpay else ""
        candidate_title = (
            (tpay.get("title") if tpay else None)
            or (ipay.get("title") if ipay else None)
            or make_artwork_title(path, candidate_text)
        )
        candidate_category = ipay.get("category", "") if ipay else ""

        combined_score = round(info["combined"], 4)
        print(f"  [{combined_score:.4f} = {info['text_score']:.3f}t + {info['image_score']:.3f}i] {candidate_title}")

        related.append({
            "image_path": path,
            "title": candidate_title,
            "category": candidate_category,
            "score": combined_score,
            "text_score": round(info["text_score"], 4),
            "image_score": round(info["image_score"], 4),
            "text_preview": candidate_text[:300],
            "text_full": candidate_text,
        })

        if len(related) >= top_k:
            break

    print(f"[combined] Found {len(related)} related (tw={text_weight}, iw={image_weight})")

    return {
        "selected": {
            "image_path": image_path,
            "title": selected_title,
            "category": selected_category,
            "text_preview": selected_text[:300],
            "text_full": selected_text,
        },
        "related": related,
    }


def _get_related_by_stored_vector(
    image_path,
    primary_collection,
    vector_name,
    top_k=3,
    exclude_paths=None,
    fetch_descriptions=False,
    text_collection_override=None,
):
    """
    Generic related-artwork retrieval using the artwork's stored vector.

    Steps:
    1. Fetch the artwork's stored vector from Qdrant (no local re-embedding needed).
    2. Run a nearest-neighbour query using that vector.
    3. Filter out excluded paths; optionally look up descriptions from text collection.
    """
    client = get_remote_client()

    if exclude_paths is None:
        exclude_paths = []
    exclude_paths = set(exclude_paths)

    # 1. Fetch the selected artwork's stored vector
    selected_point = _get_point_by_image_path(
        client, primary_collection, image_path, with_vectors=True
    )

    if not selected_point:
        print(f"[related] No point found for {image_path} in {primary_collection}")
        return {
            "selected": {
                "image_path": image_path,
                "title": make_artwork_title(image_path, ""),
                "text_preview": "",
                "text_full": "",
            },
            "related": [],
        }

    # Extract the stored vector
    raw_vector = selected_point.vector
    if isinstance(raw_vector, dict):
        stored_vector = raw_vector.get(vector_name)
    else:
        stored_vector = raw_vector

    if stored_vector is None:
        print(f"[related] Vector '{vector_name}' not found in point for {image_path}")
        return {
            "selected": {
                "image_path": image_path,
                "title": make_artwork_title(image_path, ""),
                "text_preview": "",
                "text_full": "",
            },
            "related": [],
        }

    # Build selected item metadata
    selected_category = selected_point.payload.get("category", "")
    if fetch_descriptions:
        selected_text, selected_title = _lookup_text_description(client, image_path, text_collection_override)
        selected_title = selected_point.payload.get("title") or selected_title
    else:
        selected_text = selected_point.payload.get("section_text", "")
        selected_title = (
            selected_point.payload.get("title")
            or make_artwork_title(image_path, selected_text)
        )

    print(f"[related] Selected: {selected_title} | mode={primary_collection}/{vector_name}")

    # 2. Query for nearest neighbours using the stored vector
    search_limit = max(top_k + 20, top_k + len(exclude_paths) + 10)
    search_limit = min(search_limit, 100)

    response = client.query_points(
        collection_name=primary_collection,
        query=stored_vector,
        using=vector_name,
        limit=search_limit,
        with_payload=True,
        with_vectors=False,
    )

    results = response.points

    # 3. Filter and build related list
    related = []
    seen = set()

    for r in results:
        candidate_path = r.payload.get("image_path")

        if not candidate_path:
            continue
        if candidate_path == image_path:
            continue
        if candidate_path in exclude_paths:
            continue
        if candidate_path in seen:
            continue

        seen.add(candidate_path)

        if fetch_descriptions:
            candidate_text, candidate_title = _lookup_text_description(client, candidate_path, text_collection_override)
            candidate_title = r.payload.get("title") or candidate_title
        else:
            candidate_text = r.payload.get("section_text", "")
            candidate_title = (
                r.payload.get("title")
                or make_artwork_title(candidate_path, candidate_text)
            )

        print(f"  [{r.score:.4f}] {candidate_title}")

        related.append({
            "image_path": candidate_path,
            "title": candidate_title,
            "category": r.payload.get("category", ""),
            "score": round(float(r.score), 4),
            "text_preview": candidate_text[:300],
            "text_full": candidate_text,
        })

        if len(related) >= top_k:
            break

    print(f"[related] Found {len(related)} related (excluded {len(exclude_paths)} existing nodes)")

    return {
        "selected": {
            "image_path": image_path,
            "title": selected_title,
            "category": selected_category,
            "text_preview": selected_text[:300],
            "text_full": selected_text,
        },
        "related": related,
    }


# ---------------------------------------------------------------------------
# Query-targeted expansion
# ---------------------------------------------------------------------------

def _get_related_query_targeted(image_path, query, top_k=3,
                                 exclude_paths=None, query_weight=0.4,
                                 text_collection=None):
    """
    Query-targeted graph expansion.

    Blends the selected artwork's stored text vector with an embedding of
    the original search query, then searches the text collection with the
    combined vector.  This steers expansion toward artworks that are both
    similar to the clicked artwork AND relevant to the user's original intent.

    query_weight — how strongly the query pulls results (0 = pure artwork
                   similarity, 1 = pure query similarity, 0.4 is default).
    """
    client = get_remote_client()

    if exclude_paths is None:
        exclude_paths = []
    exclude_paths = set(exclude_paths)

    _text_col = text_collection or TEXT_CLIP_COLLECTION

    # 1. Get the selected artwork's stored text vector
    text_point = _get_point_by_image_path(
        client, _text_col, image_path, with_vectors=True
    )

    if not text_point:
        print(f"[query_targeted] No text point found for {image_path}, falling back to text_clip")
        return _get_related_by_stored_vector(
            image_path=image_path,
            primary_collection=_text_col,
            vector_name="text_vector",
            top_k=top_k,
            exclude_paths=exclude_paths,
        )

    raw = text_point.vector
    artwork_vec = np.array(raw.get("text_vector") if isinstance(raw, dict) else raw,
                           dtype=np.float32)

    # 2. Embed the original query in the same vector space (MiniLM, 384-dim)
    query_vec = np.array(embed_query_minilm(query), dtype=np.float32)

    # 3. Blend: (1 - query_weight) * artwork + query_weight * query
    artwork_weight = 1.0 - query_weight
    combined = artwork_vec * artwork_weight + query_vec * query_weight

    # Renormalize so cosine similarity remains meaningful
    norm = np.linalg.norm(combined)
    if norm > 0:
        combined = combined / norm
    combined_list = combined.tolist()

    # Selected item metadata
    selected_text = text_point.payload.get("section_text", "")
    selected_title = (
        text_point.payload.get("title")
        or make_artwork_title(image_path, selected_text)
    )

    print(f"[query_targeted] Selected: {selected_title}")
    print(f"  query='{query}' | query_weight={query_weight:.2f} | artwork_weight={artwork_weight:.2f}")

    # 4. Query with the blended vector
    search_limit = max(top_k + 20, top_k + len(exclude_paths) + 10)
    search_limit = min(search_limit, 100)

    response = client.query_points(
        collection_name=_text_col,
        query=combined_list,
        using="text_vector",
        limit=search_limit,
        with_payload=True,
        with_vectors=False,
    )

    # 5. Filter and build result list
    related = []
    seen = set()

    for r in response.points:
        candidate_path = r.payload.get("image_path")
        if not candidate_path or candidate_path == image_path:
            continue
        if candidate_path in exclude_paths or candidate_path in seen:
            continue
        seen.add(candidate_path)

        candidate_text = r.payload.get("section_text", "")
        candidate_title = (
            r.payload.get("title")
            or make_artwork_title(candidate_path, candidate_text)
        )

        print(f"  [{r.score:.4f}] {candidate_title}")

        related.append({
            "image_path": candidate_path,
            "title": candidate_title,
            "category": r.payload.get("category", ""),
            "score": round(float(r.score), 4),
            "text_preview": candidate_text[:300],
            "text_full": candidate_text,
        })

        if len(related) >= top_k:
            break

    print(f"[query_targeted] Found {len(related)} related")

    return {
        "selected": {
            "image_path": image_path,
            "title": selected_title,
            "category": "",
            "text_preview": selected_text[:300],
            "text_full": selected_text,
        },
        "related": related,
    }


# ---------------------------------------------------------------------------
# Search (used by /retrieve)
# ---------------------------------------------------------------------------

def _search_collection(collection_name, vector_name, q_emb, top_k):
    client = get_remote_client()
    response = client.query_points(
        collection_name=collection_name,
        query=q_emb,
        using=vector_name,
        limit=top_k,
        with_payload=True,
    )
    return response.points


def search_text_collection(question, top_k, description_source="legacy"):
    # All text collections use MiniLM (384-dim)
    q_emb = embed_query_minilm(question)
    collection = get_text_collection(description_source)
    return _search_collection(collection, "text_vector", q_emb, top_k)


def search_image_collection(question, top_k):
    # Image collection uses CLIP-L14 text encoder (768-dim) for text-to-image search
    q_emb = embed_query_clip(question)
    return _search_collection(IMAGE_CLIP_COLLECTION, "image_vector", q_emb, top_k)


def _prepare_response(question, top_k, sorted_results):
    selected = sorted_results[:top_k]
    response = []
    print(f"\nTop {top_k} results for query: '{question}'\n")
    for i, item in enumerate(selected, start=1):
        point = item.get("point")
        if isinstance(point, list):
            first_point = point[0] if point else None
        else:
            first_point = point
        image_path = first_point.payload.get("image_path", "N/A") if first_point else "N/A"
        score = item.get("score", getattr(first_point, "score", float("nan")))
        print(f"{i}. [Score: {score:.4f}] ({image_path})")
        response.append(image_path)
    return response


def query_text_collection(question, top_k=5, description_source="legacy"):
    OVERHIT = 5
    text_results = search_text_collection(question, top_k * OVERHIT, description_source)

    combined = {}
    for r in text_results:
        img_path = r.payload.get("image_path", "N/A")
        if img_path in combined:
            combined[img_path]["score"] += r.score
            combined[img_path]["point"].append(r)
        else:
            combined[img_path] = {"point": [r], "score": r.score}

    sorted_results = sorted(combined.values(), key=lambda x: x["score"], reverse=True)
    return _prepare_response(question, top_k, sorted_results)


def query_image_collection(question, top_k=5):
    image_results = search_image_collection(question, top_k=top_k)
    image_list = [{"point": r, "score": r.score} for r in image_results]
    sorted_results = sorted(image_list, key=lambda x: x["score"], reverse=True)
    return _prepare_response(question, top_k, sorted_results)


def query_image_and_text_collection(question, top_k=5, text_weight=0.5, image_weight=0.5):
    OVERHIT = 5
    image_results = search_image_collection(question, top_k)
    text_results = search_text_collection(question, top_k * OVERHIT)

    combined = {}
    for r in image_results:
        img_path = r.payload.get("image_path", "N/A")
        combined[img_path] = {"point": [r], "score": r.score * image_weight}

    for r in text_results:
        img_path = r.payload.get("image_path", "N/A")
        if img_path in combined:
            combined[img_path]["score"] += r.score * text_weight
            combined[img_path]["point"].append(r)
        else:
            combined[img_path] = {"point": [r], "score": r.score * text_weight}

    sorted_results = sorted(combined.values(), key=lambda x: x["score"], reverse=True)
    return _prepare_response(question, top_k, sorted_results)
