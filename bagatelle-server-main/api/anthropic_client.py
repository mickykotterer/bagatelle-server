import base64
import os
from anthropic import Anthropic
import logging
from src.content_provider import get_full_paths, encode_image_with_type, get_html_content
from anthropic import APIError


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    logger.error("❌ Configuration error: ANTHROPIC_API_KEY not found in environment or .env file.")
    raise RuntimeError(
        "Configuration error: ANTHROPIC_API_KEY not found. "
        "Please set it as an environment variable or in your .env file."
    )

# Initialize Claude client
llm_client = Anthropic(api_key=ANTHROPIC_API_KEY)


def get_image_description_from_file(image_path, question="Describe this image", model="claude-sonnet-4-20250514"):
    """
    Uses Anthropic Claude 3.5 to generate a description of an image.
    """
    try:
        # Encode the image to base64
        def encode_image(image_path):
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")

        base64_image = encode_image(image_path)

        # Claude API call with multimodal input
        response = llm_client.messages.create(
            model=model,
            max_tokens=4000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image,
                            },
                        },
                    ],
                }
            ],
        )

        # Return Claude’s textual output
        return response.content[0].text

    except Exception as e:
        return str(e)


def ask_anthropic_llm(question, image_paths, prompt, model="claude-sonnet-4-20250514"):
    full_paths = get_full_paths(image_paths)
    if not full_paths:
        return "Error: No images could be loaded. Please check the image paths."

    content = [
        {"type": "text", "text": prompt},
    ]

    image_inputs = [encode_image_with_type(path) for path in full_paths]

    for img in image_inputs:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img["type"],
                "data": img["data"],
            },
        })

    # Add the main question
    content.append({"type": "text", "text": f"Question: {question}"})

    # Send to Claude API
    try:
        response = llm_client.messages.create(
            model=model,
            max_tokens=4000,
            messages=[{"role": "user", "content": content}],
            timeout=120
        )

        # Extract text blocks from response
        return "".join(
            block.text for block in response.content if block.type == "text"
        )

    except APIError as e:
        print(f"⚠️ Anthropic API error: {e}")
        return "LLM request failed due to an Anthropic API error."

    except Exception as e:
        print(f"⚠️ Unexpected error in Claude request: {e}")
        return "LLM request failed: service temporarily unavailable or timed out."


def ask_anthropic_llm_html(question, html_paths, prompt, model="claude-sonnet-4-20250514"):
    if not html_paths:
        return "Error: No HTML paths provided."

    html_pages = get_html_content(html_paths)

    # Build content blocks for Claude API
    content_blocks = [
        {"type": "text", "text": prompt},
    ]

    # Add HTML page text blocks
    for i, html in enumerate(html_pages, start=1):
        content_blocks.append({
            "type": "text",
            "text": f"HTML Page {i}:\n{html}"
        })

    # Add user question
    content_blocks.append({"type": "text", "text": f"Question: {question}"})

    # Call Anthropic API
    try:
        response = llm_client.messages.create(
            model=model,
            max_tokens=4000,
            messages=[{"role": "user", "content": content_blocks}],
            timeout=120
        )

        # Extract only text blocks from the output
        resp = "".join(
            block.text for block in response.content if block.type == "text"
        )
        # content = '\n'.join(content_blocks)
        # print("Prompt", content)
        return resp

    except APIError as e:
        print(f"⚠️ Anthropic API error: {e}")
        return "LLM request failed due to an Anthropic API error."

    except Exception as e:
        print(f"⚠️ Unexpected error in Claude request: {e}")
        return "LLM request failed: service temporarily unavailable or timed out."
