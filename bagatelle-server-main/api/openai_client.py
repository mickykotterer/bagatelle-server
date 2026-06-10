import os
from openai import OpenAI
import logging
from src.content_provider import get_full_paths, get_html_content, encode_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("❌ Configuration error: OPENAI_API_KEY not found in environment or .env file.")
    raise RuntimeError(
        "Configuration error: OPENAI_API_KEY not found. "
        "Please set it as an environment variable or in your .env file."
    )

llm_client = OpenAI(api_key=OPENAI_API_KEY)


def get_image_description_from_file(image_path, question, model="gpt-5"):
    try:
        # Getting the base64 string
        base64_image = encode_image(image_path)

        response = llm_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        }
                    ],
                }
            ])
        return response.choices[0].message.content
    except Exception as e:
        return str(e)


def ask_openai_llm(question, image_paths, prompt, model="gpt-5"):
    full_paths = get_full_paths(image_paths)
    if not full_paths:
        return "Error: No images could be loaded. Please check the image paths."

    image_inputs = [encode_image(path) for path in full_paths]

    try:
        resp = llm_client.chat.completions.create(
            model=model,
            timeout=120,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        *[
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image}"
                                }
                            }
                            for image in image_inputs
                        ],
                        {"type": "text", "text": f"Question: {question}"}
                    ]
                }
            ]
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"⚠️ LLM request failed: {e}")
        return "LLM request failed: service temporarily unavailable or timed out"


def ask_openai_llm_html(question, html_paths, prompt, model="gpt-5"):
    if not html_paths:
        return "Error: No HTML paths provided."

    html_pages = get_html_content(html_paths)

    # Build message content
    content_blocks = [{"type": "text", "text": prompt}]

    # Add each HTML page as its own text block
    for i, html in enumerate(html_pages, start=1):
        content_blocks.append({
            "type": "text",
            "text": f"HTML Page {i}:\n{html}"
        })

    # Add the question at the end
    content_blocks.append({
        "type": "text",
        "text": f"Question: {question}"
    })

    try:
        resp = llm_client.chat.completions.create(
            model=model,
            timeout=120,
            messages=[
                {
                    "role": "user",
                    "content": content_blocks
                }
            ]
        )
        # content = '\n'.join(content_blocks)
        # print("Prompt", content)
        return resp.choices[0].message.content

    except Exception as e:
        print(f"⚠️ LLM request failed: {e}")
        return "LLM request failed: service temporarily unavailable or timed out"
