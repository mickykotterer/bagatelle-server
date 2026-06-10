from api.qdrant_remote_client import get_remote_client
from sentence_transformers import SentenceTransformer
from qdrant_client.models import Filter, FieldCondition, MatchValue

# Collections
TEXT_CLIP_COLLECTION = "bagatelle_text_CLIP-L14"
IMAGE_CLIP_COLLECTION = "bagatelle_image_CLIP-L14"

# Embedding models — loaded lazily to avoid startup cost
_clip_model = None

def _get_clip_model():
    global _clip_model
    if _clip_model is None:
        _clip_model = SentenceTransformer("clip-ViT-L-14")
    return _clip_model

def embed_query_clip(text):
    """768-dim CLIP-L14 text embedding — matches the supervisor CLIP collections."""
    return _get_clip_model().encode(text).tolist()

# Keep legacy name used elsewhere
def embed_query(text):
    return embed_query_clip(text)


# ---------------------------------------------------------------------------
# Title helper
# ---------------------------------------------------------------------------

def make_artwork_title(image_path, text):
    """
    Create a readable display title from LLM-generated text.
    Falls back to cleaned filename if no useful title is found.
    """
    filename = image_path.split("/")[-1]
    fallback = filename.rsplit(".", 1)[0]

    if not text:
        return fallback

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    bad_phrases = [
        "art historical and biomedical analysis",
        "historical and biomedical analysis",
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
        "references and citations"
    ]

    for line in lines[:12]:
        cleaned = line.strip()
        lower = cleaned.lower()

        if any(phrase in lower for phrase in bad_phrases):
            continue
        if len(cleaned) > 100:
            continue
        if "." in cleaned and len(cleaned.split()) <= 3:
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


def _lookup_text_description(client, image_path):
    """
    Return (section_text, title) from the text CLIP collection for an image_path.
    Used by image mode to enrich results with descriptions.
    """
    point = _get_point_by_image_path(client, TEXT_CLIP_COLLECTION, image_path)
    if point:
        text = point.payload.get("section_text", "")
        title = point.payload.get("title") or make_artwork_title(image_path, text)
        return text, title
    return "", make_artwork_title(image_path, "")


# ---------------------------------------------------------------------------
# Core: get_related_artworks — dispatches by mode
# ---------------------------------------------------------------------------

def get_related_artworks(image_path, top_k=3, exclude_paths=None, mode="text_clip"):
    """
    Find artworks related to `image_path` using the selected graph mode.

    mode:
      "text_clip"  — semantic text similarity using CLIP-L14 text vectors
                     (bagatelle_text_CLIP-L14, text_vector)
      "image_clip" — visual similarity using CLIP-L14 image vectors
                     (bagatelle_image_CLIP-L14, image_vector)
    """
    if mode == "image_clip":
        return _get_related_by_stored_vector(
            image_path=image_path,
            primary_collection=IMAGE_CLIP_COLLECTION,
            vector_name="image_vector",
            top_k=top_k,
            exclude_paths=exclude_paths,
            fetch_descriptions=True,   # image collection has no section_text
        )
    else:
        # Default: text_clip
        return _get_related_by_stored_vector(
            image_path=image_path,
            primary_collection=TEXT_CLIP_COLLECTION,
            vector_name="text_vector",
            top_k=top_k,
            exclude_paths=exclude_paths,
            fetch_descriptions=False,
        )


def _get_related_by_stored_vector(
    image_path,
    primary_collection,
    vector_name,
    top_k=3,
    exclude_paths=None,
    fetch_descriptions=False,
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
        stored_vector = raw_vector  # unnamed single-vector collection

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
    if fetch_descriptions:
        selected_text, selected_title = _lookup_text_description(client, image_path)
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
            candidate_text, candidate_title = _lookup_text_description(client, candidate_path)
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


def search_text_collection(question, top_k):
    q_emb = embed_query_clip(question)
    return _search_collection(TEXT_CLIP_COLLECTION, "text_vector", q_emb, top_k)


def search_image_collection(question, top_k):
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


def query_text_collection(question, top_k=5):
    OVERHIT = 5
    text_results = search_text_collection(question, top_k * OVERHIT)

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
