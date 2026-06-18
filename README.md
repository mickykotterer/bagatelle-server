# Bagatelle — Knowledge Graph Exploration of Art in Medicine

This is a bachelor thesis project (University of Amsterdam). It extends the original Bagatelle artwork server with a knowledge graph layer: instead of keyword search, users navigate ~600 art-in-medicine artworks by following semantic connections.

**Original Bagatelle server:** https://github.com/albatros13/bagatelle-server

---

## Setup

**Requirements:** Python 3.10+, API keys for Qdrant, Anthropic, and optionally OpenAI.

```bash
git clone https://github.com/mickykotterer/bagatelle-server
cd bagatelle-server
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
BAGATELLE_SECRET_KEY=any-secret-string
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your-qdrant-key
ANTHROPIC_API_KEY=your-anthropic-key
OPENAI_API_KEY=your-openai-key        # optional, for GPT-5 features
```

Then run:

```bash
python app.py
```

Open http://localhost:5000 and log in with password `show-demo`.

**Note:** The CLIP image model (~1.7 GB) downloads automatically on first use and is cached after that.

---

## What's in the app

**[A.] Search for images** — enter a text query to find artworks by description (text), visual appearance (image), or both (combined). Optional LLM refinement filters results that don't match the query.

**Graph exploration** — click any artwork to build a semantic graph. Five modes:

- **Text** — nearest neighbours by MiniLM embedding of LLM-generated descriptions. Best for medical theme, diagnosis, historical context.
- **Image** — nearest neighbours by CLIP visual embedding. Best for visual style, medium, composition.
- **Combined** — blends text + image scores with a configurable weight slider.
- **Query-targeted** — steers expansion toward a concept you type (e.g. "surgery as public spectacle").
- **LLM-confirmed** — any of the above modes with Claude validating each edge and writing a short explanation before it is drawn.

Hover any graph node and click ℹ to read the full LLM description without leaving the graph.


**Evaluation mode** (/eval) — side-by-side three-panel interface (text / image / combined) used for the thesis expert study. Rate strategy preference, click edges to rate individual connections, submit results to `evaluations/results.json`.

---

## Qdrant collections needed

| Purpose | Collection name | Model |
|---|---|---|
| Text search (default) | `bagatelle_text_CLIP-L14` | MiniLM 384-dim |
| Text search (Claude) | `bagatelle_text_claude` | MiniLM 384-dim |
| Text search (GPT-5) | `bagatelle_text_gpt5` | MiniLM 384-dim |
| Image search | `bagatelle_image_CLIP-L14` | CLIP ViT-L/14 768-dim |
| Image search (OpenCLIP) | `bagatelle_image_openclip` | OpenCLIP ViT-L-14 768-dim |
| Image search (SigLIP 2) | `bagatelle_image_siglip2` | SigLIP 2 so400m 1152-dim |

To build collections: `python build_text_collection.py --model gpt4o|claude|gpt5|legacy` and `python build_image_collection.py --model clip|openclip|siglip2`. Run `python create_qdrant_indexes.py` after building each collection.

---

## Key files

- `app.py` — Flask routes
- `src/qdrant_bagatelle_store_client.py` — all retrieval and graph logic
- `templates/gallery.html` + `static/js/gallery.js` — main exploration UI
- `templates/eval.html` — three-panel evaluation interface
- `static/data/file_list_html.csv` — artwork catalogue
- `mass_test.py` — automated quantitative evaluation (16 seeds × 3 modes × N hops)
