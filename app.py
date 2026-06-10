import csv
import json
from flask import Flask, render_template, request, redirect, jsonify, session
from datetime import timedelta
from flask_toastr import Toastr
from src.qdrant_bagatelle_store_client import (
    query_image_collection,
    query_text_collection,
    query_image_and_text_collection,
    get_related_artworks,
    make_artwork_title
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
            images.append({"name": row[0], "category": row[1], "link": row[2], "title": make_artwork_title(row[0], "")})
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
    data = request.get_json(silent=True, force=True)
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

    search_mode = data.get("search_mode", "text")  # "text" | "image" | "combined"
    description_source = data.get("description_source", "legacy")  # "legacy"|"gpt4o"|"claude"|"gpt5"

    image_paths = []
    if question:
        try:
            if search_mode == "image":
                logger.info(f"Image search: {question}")
                image_paths = query_image_collection(question, top_k)
            elif search_mode == "combined":
                logger.info(f"Combined search: {question}")
                image_paths = query_image_and_text_collection(question, top_k)
            else:
                logger.info(f"Text search [{description_source}]: {question}")
                image_paths = query_text_collection(question, top_k, description_source)

            # LLM refinement: filter results that don't match the query
            if llm_model and image_paths:
                try:
                    logger.info(f"Refining {len(image_paths)} results with LLM ({llm_model})")
                    image_paths = refine_response(question, image_paths, llm_model)
                    logger.info(f"After refinement: {len(image_paths)} results kept")
                except Exception as e:
                    logger.warning(f"LLM refinement failed, returning unfiltered results: {e}")

            return jsonify({"response": image_paths})

        except Exception as e:
            print(e)
            return jsonify({"response": image_paths, "error": str(e)})

def make_edge_explanation(selected_item, related_item, llm_model=None):
    """Generate a short explanation for why two artworks are related (no judgement)."""
    selected_title = selected_item.get("title", "Selected artwork")
    related_title  = related_item.get("title", "Related artwork")
    selected_text  = (selected_item.get("text_full", "") or selected_item.get("text_preview", ""))[:2500]
    related_text   = (related_item.get("text_full",  "") or related_item.get("text_preview",  ""))[:2500]

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
        return ask_text_llm(prompt, llm_model=llm_model).strip()
    except Exception as e:
        logger.warning(f"Edge explanation failed: {e}")
        return ""


def llm_judge_edge(selected_item, related_item, llm_model=None):
    """
    Goal 5: LLM-confirmed graph edges.

    Judges whether a Qdrant-retrieved connection is actually meaningful and
    generates a relation type + explanation in a single LLM call.

    Returns a dict:
      {
        "judgement":    "yes" | "maybe" | "no",
        "relation_type": "<2-4 word label>",
        "explanation":  "<short sentence>"
      }
    """
    import json as _json

    selected_title = selected_item.get("title", "Selected artwork")
    related_title  = related_item.get("title", "Related artwork")
    selected_text  = (selected_item.get("text_full", "") or selected_item.get("text_preview", ""))[:1800]
    related_text   = (related_item.get("text_full",  "") or related_item.get("text_preview",  ""))[:1800]

    prompt = f"""You are evaluating a proposed connection in a medical-art knowledge graph.

SELECTED ARTWORK
Title: {selected_title}
Description: {selected_text}

CANDIDATE ARTWORK
Title: {related_title}
Description: {related_text}

Decide whether this connection is meaningful for a viewer exploring medical art history.

Respond with ONLY a valid JSON object — no markdown, no extra text:
{{
  "judgement": "yes",
  "relation_type": "2-4 word label",
  "explanation": "one sentence, max 35 words"
}}

judgement rules:
- "yes"   — connection is medically, historically, or artistically meaningful
- "maybe" — connection is plausible but weak or indirect
- "no"    — connection is coincidental or superficial (e.g. only similar medium/era)
""".strip()

    default = {"judgement": "maybe", "relation_type": "", "explanation": ""}

    try:
        raw = ask_text_llm(prompt, llm_model=llm_model).strip()
        # Strip markdown fences if the model wraps in ```json
        raw = raw.strip("`").removeprefix("json").strip()
        result = _json.loads(raw)
        judgement = result.get("judgement", "maybe").lower()
        if judgement not in ("yes", "no", "maybe"):
            judgement = "maybe"
        return {
            "judgement":    judgement,
            "relation_type": result.get("relation_type", ""),
            "explanation":  result.get("explanation", ""),
        }
    except Exception as e:
        logger.warning(f"LLM edge judgement failed: {e}")
        return default

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

    mode               = data.get("mode", "text_clip")
    description_source = data.get("description_source", "legacy")
    image_model        = data.get("image_model", "clip")

    try:
        text_weight = float(data.get("text_weight", 0.5))
        image_weight = float(data.get("image_weight", 0.5))
        query_weight = float(data.get("query_weight", 0.4))
    except (TypeError, ValueError):
        text_weight, image_weight, query_weight = 0.5, 0.5, 0.4

    query = data.get("query") or None

    try:
        logger.info(f"Finding related artworks for {image_path} [mode={mode}, desc={description_source}]")
        related_data = get_related_artworks(
            image_path, top_k,
            exclude_paths=exclude_paths,
            mode=mode,
            text_weight=text_weight,
            image_weight=image_weight,
            query=query,
            query_weight=query_weight,
            description_source=description_source,
            image_model=image_model,
        )

        llm_model   = data.get("llm")
        llm_confirm = bool(data.get("llm_confirm", False))

        selected_item = related_data.get("selected", {})
        related_items = related_data.get("related", [])

        if llm_confirm:
            # Goal 5: judge + explain in one call per candidate
            for item in related_items:
                verdict = llm_judge_edge(
                    selected_item=selected_item,
                    related_item=item,
                    llm_model=llm_model,
                )
                item["llm_judgement"]  = verdict["judgement"]
                item["relation_type"]  = verdict["relation_type"]
                item["edge_explanation"] = verdict["explanation"]
        else:
            # Standard path: explanation only, no judgement
            for item in related_items:
                item["edge_explanation"] = make_edge_explanation(
                    selected_item=selected_item,
                    related_item=item,
                    llm_model=llm_model,
                )
                item["llm_judgement"] = None
                item["relation_type"] = ""

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


@app.route('/eval')
def eval_page():
    if not session.get("logged_in"):
        return redirect('/')
    bagatelle_data = load_bagatelle_file_list()
    return render_template("eval.html", bagatelle_data=json.dumps(bagatelle_data))


@app.route('/submit_evaluation', methods=['POST'])
def submit_evaluation():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data received"}), 400

    eval_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'evaluations')
    os.makedirs(eval_dir, exist_ok=True)
    results_file = os.path.join(eval_dir, 'results.json')

    results = []
    if os.path.exists(results_file):
        try:
            with open(results_file, 'r') as f:
                results = json.load(f)
        except Exception:
            results = []

    from datetime import datetime
    data['server_timestamp'] = datetime.now().isoformat()
    results.append(data)

    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    logger.info(f"Evaluation saved. Total entries: {len(results)}")
    return jsonify({"success": True, "total_entries": len(results)})


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
    app.run(debug=True)