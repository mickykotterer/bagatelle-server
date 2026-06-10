import os
from qdrant_client import QdrantClient
import logging
from importlib.metadata import version

print("Qdrant client version:", version("qdrant-client"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
if not (QDRANT_URL and QDRANT_API_KEY):
    logger.error("❌ Configuration error: QDRANT_URL or QDRANT_API_KEY not found in environment or .env file.")
    raise RuntimeError(
        "Configuration error: QDRANT_URL or QDRANT_API_KEY not found. "
        "Please set it as an environment variable or in your .env file."
    )

def get_remote_client():
    return QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        https=True
)
