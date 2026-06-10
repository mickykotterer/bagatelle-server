from api.qdrant_remote_client import get_remote_client
from qdrant_client.models import PayloadSchemaType

TEXT_COLLECTION = "bagatelle_text_CLIP-L14"
IMAGE_COLLECTION = "bagatelle_image_CLIP-L14"

print("Starting index creation...")

client = get_remote_client()
print("Connected to Qdrant")

# Text collection — image_path index (needed for filtered lookups in /related)
client.create_payload_index(
    collection_name=TEXT_COLLECTION,
    field_name="image_path",
    field_schema=PayloadSchemaType.KEYWORD,
)
print(f"✅ Created payload index for image_path on {TEXT_COLLECTION}")

# Image collection — image_path index (needed for filtered lookups in image_clip mode)
client.create_payload_index(
    collection_name=IMAGE_COLLECTION,
    field_name="image_path",
    field_schema=PayloadSchemaType.KEYWORD,
)
print(f"✅ Created payload index for image_path on {IMAGE_COLLECTION}")

print("Done.")
