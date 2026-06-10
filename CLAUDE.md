# Bagatelle — Thesis Project Context

## What this project is
A knowledge graph-based exploration system for ~600 art-in-medicine artworks.
Built on top of the existing Bagatelle Flask server (Flask + Qdrant + CLIP/MiniLM embeddings).

The thesis goal: turn a search-results interface into a semantically navigable graph,
comparing five graph generation strategies (text, image, combined, query-targeted, LLM-confirmed).
Thesis drafts:
- `Thesis/Exploring Art in Medicine through Knowledge Graphs (1).pdf` — original PDF
- `Thesis/thesis_gonogo.docx` — updated go/no-go Word version
- `Thesis/thesis_gonogo.tex` — Overleaf-ready LaTeX version

## Thesis structure (for context when writing/evaluating)
- Ch 1: Introduction — gap between keyword search and meaningful exploration of art-in-medicine collections
- Ch 2: Background — cultural heritage systems, CLIP/LLMs, knowledge graphs, exploratory search evaluation
- Ch 3: System Design — graph schema, 5 strategies, exclusion mechanism, interface design
- Ch 4: Implementation — backend, Qdrant setup, embedding pipeline, LLM integration, JS graph engine
- Ch 5: Evaluation — 5.1 evaluation design written (3 components, MD evaluator engaged); 5.2–5.4 are placeholders; 5.5 Results is empty (awaiting study)
- Ch 6: Discussion — strategy comparison, LLM explanations, search vs. exploration tension, limitations
- Ch 7: Conclusion

## Key files
- `app.py` — Flask routes (/retrieve, /related, /generate_program, /eval, /submit_evaluation)
- `src/qdrant_bagatelle_store_client.py` — all retrieval logic, graph modes, title extraction
- `templates/gallery.html` — gallery UI template (loaded via SPA in index.html)
- `templates/eval.html` — standalone evaluation UI (full HTML page, not SPA-loaded)
- `static/js/gallery.js` — frontend: graph rendering, stats, mode selectors, exploration field
- `static/styles/gallery_style.css` — graph node, card, category badge, judgement styles
- `evaluations/results.json` — created on first submission; all evaluation ratings appended here
- `create_qdrant_indexes.py` — run once after building any new collection
- `build_text_collection.py` — builds text collections; use --model gpt4o|claude|gpt5|legacy
- `build_image_collection.py` — builds image collections; use --model clip|openclip|siglip2
- `Thesis/Notes project.pdf` — full development log (sections 1–49)
- `Thesis/Notes project supplement.md` — continuation notes from section 50 onwards

## Qdrant collections
### Text (all 384-dim MiniLM, vector name: text_vector)
| collection | descriptions | status |
|---|---|---|
| `bagatelle_text_CLIP-L14` | GPT-4o (legacy, default) | ✅ built |
| `bagatelle_text_claude` | Claude sonnet-4 | ✅ built |
| `bagatelle_text_gpt5` | GPT-5 | ✅ built |
| `bagatelle_text_gpt4o` | GPT-4o (clean name) | not built yet |

### Image (vector name: image_vector)
| collection | model | dim | status |
|---|---|---|---|
| `bagatelle_image_CLIP-L14` | CLIP ViT-L/14 | 768 | ✅ built |
| `bagatelle_image_openclip` | OpenCLIP ViT-L-14 | 768 | ✅ built |
| `bagatelle_image_siglip2` | SigLIP 2 so400m | 1152 | ✅ built |

**Important**: always use MiniLM for text collections, CLIP encoder for image collections.
Mixing dimensions causes a 400 error from Qdrant.

## All graph modes (get_related_artworks)
| mode | strategy | key param |
|---|---|---|
| `text_clip` | nearest neighbours by text vector | `description_source` |
| `image_clip` | nearest neighbours by image vector | `image_model` |
| `combined_clip` | merge text + image scores | `text_weight`, `image_weight` |
| `query_targeted` | blend artwork vector + query embedding | `query`, `query_weight` |

LLM confirmation (`llm_confirm=True`) can be layered on top of any mode.
Exploration question field overrides any mode to `query_targeted` with a per-hop query.

## Search modes (/retrieve)
- `text` — MiniLM query → text collection (uses `description_source`)
- `image` — CLIP text encoder → image collection
- `combined` — merge text + image scores
- LLM refine (`llm_confirm` checkbox) filters results after retrieval

## What's been completed
- Goals 1–8 fully implemented
- Goal 5: LLM-confirmed edges (yes/no/maybe + relation type + explanation, green/amber/grey styling)
- Goal 6: OpenCLIP and SigLIP 2 collections built; image model dropdown in UI
- Goal 7 (mini): optional exploration question field — overrides graph mode per-hop
- Goal 8: graph statistics panel (nodes, edges, expansions, avg/min/max score, top categories, modes used, LLM judgements)
- Description source selector (GPT-4o / Claude / GPT-5) for both search and graph
- LLM refine search re-enabled for /retrieve
- Graph stats track modes used and reset on clear
- Goal 9: artwork titles shown in catalogue (load_bagatelle_file_list now includes `title` via make_artwork_title; displayImages uses it)
- In-graph description button: hovering any graph node shows an ℹ button; clicking it renders that artwork's description card in the panel without triggering a new expansion. text_preview/text_full are now stored in graphNodes.
- **Goal 10: Evaluation UI — COMPLETE**. See details below.

## Goal 10 — Evaluation UI (completed)
Standalone page at `/eval` (login-gated, not SPA-loaded). Results saved to `evaluations/results.json`.

### Two modes
**Structured mode** — 16 pre-selected seed artworks, loaded one at a time. "Load in both panels" fetches both graphs in parallel. Query-targeted option is hidden (no free-text query in structured mode). Task counter advances automatically after each submit.

**Free mode** — evaluator searches any query, gets thumbnail results, clicks a thumbnail to open a selection lightbox (full image + "Pick this artwork" / "Choose different"), then both panels load from the chosen artwork.

### Two-panel layout
Each panel (🅐 Left / 🅑 Right) has its own independent `GraphPanel` class instance with separate node/edge Maps, mode selector (Text / Image / Combined / Query-targeted), description source selector, and query input (shown only for query-targeted). Graph rendering, stats, and expansion work identically to the main gallery but at smaller node size (110×130px). Panel graphs do not share state.

### Rating panel
Three preference questions (relevance, exploration, explanations) with Left / Tie / Right radio buttons. Free-text comments field. Submit auto-saves to server and advances to next task (structured mode). Download JSON exports the full session client-side as a backup.

### Edge rating
Clicking any edge curve opens a popup showing source → target, similarity score, and LLM explanation. Buttons: ✓ Meaningful / ~ Partial / ✗ Not meaningful. Rated edges turn green/amber/grey. All edge ratings are included in the submitted JSON.

### Node info popup
Hovering a graph node shows an ℹ button. Clicking it opens a fixed side panel with the artwork image, title, category, text preview, and a collapsible "Show full description" toggle (text_full).

### Result JSON schema (per entry)
```json
{
  "type": "structured|free",
  "evaluator": "...",
  "timestamp": "...",
  "task_index": 0,
  "artwork": { "filename": "...", "title": "...", "category": "..." },
  "left_strategy":  { "mode": "text_clip", "description_source": "legacy" },
  "right_strategy": { "mode": "image_clip", "description_source": "legacy" },
  "ratings": { "relevance": "left|tie|right", "exploration": "...", "explanations": "...", "comments": "..." },
  "edge_ratings": [{ "edgeId": "...", "panelId": "left|right", "score": 0.85, "rating": "yes|maybe|no" }],
  "graph_stats": { "left": { "nodes": 4, "edges": 3, "avg_score": 0.82, "score_variance": 0.01, ... }, "right": {...} },
  "server_timestamp": "..."
}
```

### 16 seed artworks
Selected to stress-test strategy divergence (text vs image). See `Thesis/Notes project supplement.md` section 52 for full rationale.
1. Japanese Smallpox Manuscript — explicit pustules, medical illustration
2. Dalton Rash of Sores (1856) — Western clinical medical illustration, same disease as #1
3. Mona Lisa (LDL diagnosis) — no visible condition, purely textual medical reading
4. Gentileschi Judith (goiter) — barely-visible endocrine condition on maid's neck
5. Caravaggio Sleeping Cupid (hormonal) — chubby child, no obvious medical visual signal
6. Michelangelo Night (breast cancer) — sculpture, retroactive oncology diagnosis
7. Rembrandt Anatomy Lesson — iconic, both visually and textually unambiguous (control)
8. Young Venetian Woman Before/After Cholera (1831) — clinical before/after illustration
9. Bruegel The Beggars (1568) — visible disabilities, but also symbolic
10. Zumbo The Plague (17th C.) — wax sculpture, visually unlike any painting in collection
11. Fuseli The Nightmare (1781) — Romantic supernatural; psychiatric only via text
12. Munch The Sick Child (1885) — Expressionist; tuberculosis connection is textual
13. Ribera The Club Foot (1642) — visible deformity, portrait composition
14. Honthorst The Dentist (1622) — candlelit genre scene; dental only via text
15. Ancient Egyptian Medicine — papyrus painting, visually unlike all other works
16. Tamerlane (leg & hand disability) — ornate Persian court painting; disability invisible

### Known gotcha
`eval.html` must NOT include `gallery_style.css` — it defines `.graph-node { width:140px; min-height:165px; }` which overrides the eval panel's 110×130px node sizes and breaks edge alignment. Also never add a second `.graph-node { position: relative; }` CSS rule — it overrides `position: absolute` and breaks all node placement.

## Known issues / gotchas
- Always edit project files directly (`src/`, `templates/`, `static/`) — Thesis/ subfolder is archive only
- `cp` command silently truncates large files — use Write/Edit tools instead
- SigLIP 2 `get_image_features()` returns `BaseModelOutputWithPooling` in this transformers version — use `model.vision_model(...).pooler_output` directly
- The gallery loads via SPA (index.js → /gallery AJAX); script tags must be at bottom of gallery.html
- Run `create_qdrant_indexes.py` after building any new collection
- `clip-ViT-L-14` downloads ~1.7 GB on first use (cached after that)
- `open-clip-torch` must be installed separately: `pip install open-clip-torch`

## Running the app
```
.\.venv\Scripts\python.exe app.py
```
Then open http://localhost:5000. Password: show-demo
