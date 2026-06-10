import csv
import json
from flask import Flask, render_template, request, redirect, jsonify, session
from datetime import timedelta
from flask_toastr import Toastr
from src.qdrant_bagatelle_store_client import (
    query_image_collection,
    query_text_collection,
    query_image_and_text_collection,
    get_related_artworks
)
from api.openai_client import ask_openai_llm, ask_openai_llm_html
from api.anthropic_client import ask_anthropic_llm, ask_anthropic_llm_html
import os
import logging
from dotenv import load_dotenv
import re
from anthropic import Anthropic
from openai import OpenAI

# log = logging.getLogger('werkzeug')
# log.setLevel(logging.ERROR)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app():
    if not os.getenv("BAGATELLE_SECRET_KEY"):
        logger.info("🔍 BAGATELLE_SECRET_KEY not found in environment — trying to load from .env")
        load_dotenv()
    if not os.getenv("BAGATELLE_SECRET_KEY"):
        logger.error("❌ Configuration error: BAGATELLE_SECRET_KEY not found in environment or .env file.")
        raise RuntimeError(
            "Configuration error: BAGATELLE_SECRET_KEY not found. "
            "Please set it as an environment variable or in your .env file."
        )
    app = Flask(__name__)
    app.config['SESSION_PERMANENT'] = True
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
    app.secret_key = os.getenv("BAGATELLE_SECRET_KEY")
    logger.info("✅ Flask app created successfully with loaded configuration.")
    return app


app = create_app()
toastr = Toastr(app)


def load_bagatelle_file_list():
    file_name = os.path.join('static', 'data', 'file_list_html.csv')
    images = []
    with open(file_name, 'r') as csv_file:
        reader = csv.reader(csv_file, delimiter=',')
        next(reader, None)
        for row in reader:
            images.append({"name": row[0], "category": row[1], "link": row[2]})
    return images


def refine_response(question, image_paths, llm_model):
    if not image_paths or len(image_paths) == 0:
        return image_paths
    if len(image_paths) > 10:
        print("Cannot process more than 10 images!")
        return image_paths

    prompt = f"""
You are an expert image analyst. Examine each of the following {len(image_paths)} images and determine 
whether it match the search query. Answer strictly with a JSON array of "Yes" or "No" values, one per image, 
in the same order as given.
Example:
["No", "Yes", "No"]    
    """
    if llm_model == "gpt-5":
        answer = ask_openai_llm(question, image_paths, prompt)
    else:
        # Default LLM - claude-sonnet-4-20250514
        answer = ask_anthropic_llm(question, image_paths, prompt)

    answers = re.findall(r"\b(?:Image\s*\d+\s*[:\-]?\s*)?(Yes|No)\b", answer, flags=re.IGNORECASE)
    print("LLM response: ", answer)
    print("LLM filter:", answers)
    filtered = [s for s, m in zip(image_paths, answers) if "yes" in m.lower()]
    return filtered

def ask_text_llm(prompt, llm_model=None):
    """
    Simple text-only LLM call for edge explanations.
    Does not require image paths or HTML paths.
    """

    if llm_model == "gpt-5":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing")

        client = OpenAI(api_key=api_key)

        response = client.responses.create(
            model="gpt-5",
            input=prompt
        )

        return response.output_text.strip()

    else:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is missing")

        client = Anthropic(api_key=api_key)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=120,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.content[0].text.strip()

@app.route('/')
def home():
    return render_template("index.html")


@app.route("/gallery")
def gallery():
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not session.get("logged_in"):
        if is_ajax:
            return jsonify({"error": "Not logged in"}), 401
        return redirect('/')
    # If logged in but this is a direct navigation, redirect to home where SPA loads it properly
    if not is_ajax:
        return redirect('/')
    bagatelle_data = load_bagatelle_file_list()
    return render_template("gallery.html", bagatelle_data=json.dumps(bagatelle_data))


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"answer": "No JSON payload received"}), 400
    user_pwd = data.get('password')
    if user_pwd == "show-demo":
        session['logged_in'] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid password"}), 401


@app.route('/retrieve', methods=['POST'])
def retrieve():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No JSON payload received"}), 400

    llm_model = data.get("llm")
    if llm_model and not session.get("logged_in"):
        return jsonify({"error": "Not logged in"}), 401

    question = data.get("question")

    try:
        top_k = int(data.get("k", 3))
    except (TypeError, ValueError):
        top_k = 3

    image_paths = []
    if question:
        try:
            logger.info("Forced text search")
            image_paths = query_text_collection(question, top_k)
            
            #temporary disabled
            #if llm_model:
            #   image_paths = refine_response(question, image_paths, llm_model)

            return jsonify({"response": image_paths})

        except Exception as e:
            print(e)
            return jsonify({"response": image_paths, "error": str(e)})

def make_edge_explanation(selected_item, related_item, llm_model=None):
    """
    Generate a short explanation for why two artworks are related.
    Uses the stored LLM-generated descriptions from Qdrant.
    """

    selected_title = selected_item.get("title", "Selected artwork")
    related_title = related_item.get("title", "Related artwork")

    selected_text = selected_item.get("text_full", "") or selected_item.get("text_preview", "")
    related_text = related_item.get("text_full", "") or related_item.get("text_preview", "")

    # Keep prompt size manageable
    selected_text = selected_text[:2500]
    related_text = related_text[:2500]

    prompt = f"""
You are explaining a semantic connection in an artwork exploration graph.

Selected artwork:
Title: {selected_title}
Description:
{selected_text}

Related artwork:
Title: {related_title}
Description:
{related_text}

Write one short explanation, maximum 45 words, explaining why these two artworks are related.
Focus on shared medical, historical, visual, symbolic, or art-historical themes.
Do not mention similarity scores. Do not say "the texts". Do not use bullet points.
""".strip()

    try:
        answer = ask_text_llm(prompt, llm_model=llm_model)
        return answer.strip()

    except Exception as e:
        logger.warning(f"Edge explanation failed: {e}")
        return ""

@app.route('/related', methods=['POST'])
def related():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No JSON payload received"}), 400

    image_path = data.get("image_path")
    
    if not image_path:
        return jsonify({"error": "Missing image_path"}), 400

    exclude_paths = data.get("exclude_paths", [])
    if not isinstance(exclude_paths, list):
        exclude_paths = []

    try:
        top_k = int(data.get("k", 3))
    except (TypeError, ValueError):
        top_k = 3

    mode = data.get("mode", "text_clip")

    try:
        logger.info(f"Finding related artworks for {image_path} [mode={mode}]")
        related_data = get_related_artworks(image_path, top_k, exclude_paths=exclude_paths, mode=mode)

        llm_model = data.get("llm")

        selected_item = related_data.get("selected", {})
        related_items = related_data.get("related", [])

        for item in related_items:
            item["edge_explanation"] = make_edge_explanation(
                selected_item=selected_item,
                related_item=item,
                llm_model=llm_model
            )

        return jsonify(related_data)

    except Exception as e:
        print(e)
        return jsonify({
            "selected": {
                "image_path": image_path,
                "text_preview": ""
            },
            "related": [],
            "error": str(e)
        }), 500

@app.route('/test_related')
def test_related():
    image_path = "static/data/images/50ThomasEakinsTheAgnewClinic1889Surgerypg201.jpg"

    related_paths = get_related_artworks(image_path, 3)

    return jsonify({
        "selected": image_path,
        "related": related_paths
    })

@app.route('/generate_program', methods=['POST'])
def generate_program():
    if not session.get("logged_in"):
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No JSON payload received"}), 400

    print("Workshop parameters:", data)
    num_days = data.get("num_days", 3)
    theme = data.get("theme", "")
    audience = data.get("audience", "")
    context = data.get("context")
    llm_model = data.get("llm")
    context_type = data.get("context_type")

    if not theme or not audience:
        return jsonify({"error": "Missing theme or audience"}), 400

    try:
        logger.info("Generating program...")
        context_paths = context.strip().splitlines()
        # Build the instruction prompt
        prompt_template = """
Using only the selected set of artworks as educational and illustrative material, create a nicely formatted 500-word programme 
for {NUM_DAYS}-day workshop on art in medicine with the theme “{THEME}” aimed at {AUDIENCE}. 
"""
        prompt = prompt_template.format(NUM_DAYS=num_days, THEME=theme, AUDIENCE=audience)
        print("Parameterized prompt:", prompt, "...")
        prompt += """
The cross-cutting topics discussed in this workshop should prioritize commonalities between the artists who created these 
works as well as the overlap in medical/historical/artistic aspects of their artifacts. Before you describe the workshop 
programme in any detail, first provide a 100-word introduction that explains why the chosen theme of the art-in-medicine 
workshop is relevant to the type of audience the workshop is aimed at, and why the selected artworks provide very apt 
and fitting case-studies for the theme of the workshop. Create a programme that is focused on the chosen theme, in the 
style of an academic syllabus, introducing each day with a short overview and set of learning objectives, and specifying 
the educational goals for each session and the artworks and corresponding topics that are explored. Please make sure that 
each workshop day has sessions covering the typical 9am-to-5pm span (with appropriate breaks for coffee, lunch etc) - 
also propose break-out sessions for small-group discussions that combine the chosen artworks and workshop theme. 
In the programme, mention the artworks by name and explicitly point out in which sessions they will 
be discussed and why. Provide response in HTML format. Do not refer to instructions or ask questions in response.
""".strip()
        content = prompt
        if context_type == "images":
            if llm_model == "gpt-5":
                llm_resp = ask_openai_llm("", context_paths, prompt)
            else:
                llm_resp = ask_anthropic_llm("", context_paths, prompt)
        else:
            if llm_model == "gpt-5":
                llm_resp = ask_openai_llm_html("", context_paths, prompt)
            else:
                llm_resp = ask_anthropic_llm_html("", context_paths, prompt)
        return jsonify({"response": llm_resp, "content": content})
    except Exception as e:
        print(e)
        return jsonify({"error": "Model failed to run!", "details": str(e)}), 500


@app.route('/session')
def session_status():
    """Return JSON with current login status."""
    return jsonify({"logged_in": bool(session.get("logged_in"))})


@app.route('/back')
def back():
    """
    A button to redirect back to the main page
    :return:
    """
    return redirect('/')


if __name__ == '__main__':
    app.run()
    app.app_context().push()
    session.pop('logged_in', None)
