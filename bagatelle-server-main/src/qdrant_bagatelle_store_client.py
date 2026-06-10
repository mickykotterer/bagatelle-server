from api.qdrant_remote_client import get_remote_client
from api.replicate_client import get_clip_embedding


def embed_query(text):
    res = get_clip_embedding({
        "text": text
    })
    return res["embedding"]


def search_image_collection(question, top_k):
    q_emb = embed_query(question)
    client = get_remote_client()
    IMAGE_COLLECTION = "bagatelle_image_CLIP-L14"

    image_results = client.search(
        collection_name=IMAGE_COLLECTION,
        query_vector=("image_vector", q_emb),
        limit=top_k,
        with_payload=["title", "image_path"]
    )
    return image_results


def search_text_collection(question, top_k):
    q_emb = embed_query(question)
    client = get_remote_client()
    TEXT_COLLECTION = "bagatelle_text_CLIP-L14"

    text_results = client.search(
        collection_name=TEXT_COLLECTION,
        query_vector=("text_vector", q_emb),
        limit=top_k,
        with_payload=["section_text", "image_path"]
    )
    return text_results


def prepare_response(question, top_k, sorted_results):
    selected = sorted_results[:top_k]
    response = []
    print(f"\nTop {top_k} results for query: '{question}'\n")
    for i, item in enumerate(selected, start=1):
        point = item.get("point")
        # Normalize: point may be a single result or a list of results
        if isinstance(point, list):
            first_point = point[0] if point else None
        else:
            first_point = point
        image_path = first_point.payload.get("image_path", "N/A") if first_point else "N/A"
        score = item.get("score", getattr(first_point, "score", float("nan")))
        print(f"{i}. [Score: {score:.4f}] ({image_path})")
        response.append(image_path)
    return response


def query_image_collection(question, top_k=5):
    image_results = search_image_collection(question, top_k=top_k)
    image_list = []
    for r in image_results:
        image_list.append({"point": r, "score": r.score})
    sorted_results = sorted(image_list, key=lambda x: x["score"], reverse=True)
    return prepare_response(question, top_k, sorted_results)


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
    return prepare_response(question, top_k, sorted_results)


def query_image_and_text_collection(question, top_k=5, text_weight=0.5, image_weight=0.5):
    OVERHIT = 5
    image_results = search_image_collection(question, top_k)
    text_results = search_text_collection(question, top_k * OVERHIT)

    combined = {}
    for r in image_results:
        img_path = r.payload.get("image_path", "N/A")
        combined[img_path] = {"point": [r], "score": r.score * text_weight}

    for r in text_results:
        img_path = r.payload.get("image_path", "N/A")
        if img_path in combined:
            combined[img_path]["score"] += r.score * image_weight
            combined[img_path]["point"].append(r)
        else:
            combined[img_path] = {"point": [r], "score": r.score * image_weight}
    sorted_results = sorted(combined.values(), key=lambda x: x["score"], reverse=True)
    return prepare_response(question, top_k, sorted_results)


def generate_curiculum():
    prompt="""
    Using the selected set of images as educational and illustrative material, 
    create a nicely formatted 500-word programme for a [NUM OF DAYS]-day workshop on art in 
    medicine with the theme “[THEME OF WORKSHOP]” aimed at [TYPE OF AUDIENCE]. 
    The cross-cutting topics discussed in this workshop should prioritize commonalities between 
    the artists who created these works as well as the overlap in medical/historical/artistic 
    themes of their artifacts. Create the programme in the style of an academic syllabus, 
    introducing each day with a short overview and learning objectives, and specifying the 
    educational goals for each session and the artworks and corresponding themes that are explored.   
    """

    sample = """
    Using the selected set of images as educational and illustrative material, create a nicely formatted 500-word programme for a 3-day workshop on art in medicine with the theme “Taking Flight” aimed at pathohistology residents. The cross-cutting topics discussed in this workshop should prioritize commonalities between the artists who created these works as well as the overlap in medical/historical/artistic themes of their artifacts. Create the programme in the style of an academic syllabus, introducing each day with a short overview and learning objectives, and specifying the educational goals for each session and the artworks and corresponding themes that are explored.   
    """