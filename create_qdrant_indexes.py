from api.qdrant_remote_client import get_remote_client
from qdrant_client.models import PayloadSchemaType
from qdrant_client.http.exceptions import UnexpectedResponse

# All collections that need an image_path keyword index
COLLECTIONS = [
    "bagatelle_text_CLIP-L14",    # legacy GPT-4o text collection
    "bagatelle_text_gpt4o",       # rebuilt GPT-4o text collection
    "bagatelle_text_claude",      # Claude sonnet-4 text collection
    "bagatelle_text_gpt5",        # GPT-5 text collection
    "bagatelle_image_CLIP-L14",   # CLIP-L14 image collection (768-dim)
    "bagatelle_image_openclip",   # OpenCLIP ViT-L-14 (768-dim)
    "bagatelle_image_siglip2",    # SigLIP 2 so400m (1152-dim)
]

print("Starting index creation...")

client = get_remote_client()
print("Connected to Qdrant\n")

for collection in COLLECTIONS:
    try:
        client.create_payload_index(
            collection_name=collection,
            field_name="image_path",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        print(f"  Created image_path index on {collection}")
    except UnexpectedResponse as e:
        if "already exists" in str(e).lower() or "409" in str(e):
            print(f"  Index already exists on {collection} — skipping")
        else:
            print(f"  Collection '{collection}' not found or error — skipping ({e})")
    except Exception as e:
        print(f"  Skipping {collection}: {e}")

print("\nDone.")
