import replicate
import os
import logging

# openai/clip, lucataco/clip-vit-base-patch32 expects os.environ["REPLICATE_API_TOKEN"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
if not REPLICATE_API_TOKEN:
    logger.error("❌ Configuration error: REPLICATE_API_TOKEN not found in environment or .env file.")
    raise RuntimeError(
        "Configuration error: REPLICATE_API_TOKEN not found. "
        "Please set it as an environment variable or in your .env file."
    )

def get_clip_embedding(input):
    output = replicate.run(
        "openai/clip",
        input=input
    )
    return output

