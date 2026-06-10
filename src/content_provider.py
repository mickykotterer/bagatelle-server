from bs4 import BeautifulSoup
import os
import re, base64
from flask import current_app
import mimetypes

def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def encode_image_with_type(path):
    """Read image as base64 and detect correct MIME type."""
    mime_type, _ = mimetypes.guess_type(path)
    if mime_type is None:
        mime_type = "image/jpeg"  # fallback for unknown types

    b64data = encode_image(path)
    return {"data": b64data, "type": mime_type}


def get_full_paths(context_paths: str):
    root_dir = current_app.root_path
    file_paths = []

    for line in context_paths:
        path = line.strip()
        if not path:
            continue
        path = re.sub(r"^\.\.?/", "", path)
        path = path.replace("\\", "/")

        full_path = os.path.join(root_dir, path)

        if os.path.isfile(full_path):
            print(f"✅ Success: File found at {full_path}")
            file_paths.append(str(full_path))
        else:
            print(f"⚠️ Warning: File not found at {full_path}")
            print(f"   Original path: {path}")
            raise RuntimeError("Failed to find paths")

    return file_paths


def get_html_content(html_paths: str):
    full_paths = get_full_paths(html_paths)
    extracted_pages = []

    for path in full_paths:
        if not os.path.isfile(path):
            print(f"⚠️ File not found: {path}")
            continue

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()

        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted elements such as scripts/styles/nav/footers
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)

        extracted_pages.append(text)

    return extracted_pages
