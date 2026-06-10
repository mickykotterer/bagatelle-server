# Bagatelle — Project Notes Supplement
_Continuation of Notes project.pdf (sections 1–49). Sections 50 onwards documented here._

---

## 50. Goal 10 Design — Evaluation Mode Architecture

Before coding, the evaluation design was planned in detail to match Chapter 5 of the thesis (sections 5.1–5.4).

**Three thesis evaluation components mapped to UI features:**
- Side-by-side strategy comparison → two-panel layout with independent graph state per panel
- Edge relevance judgments → click-to-rate popup on any edge curve
- Graph-level statistics → auto-captured from panel state on submit (nodes, edges, avg score, variance, category distribution)

**Mode decision:** Two evaluation modes in one UI rather than a separate tool:
- *Structured*: 16 pre-selected seed artworks ensure consistent, comparable data across evaluators
- *Free*: evaluator searches any query and picks any artwork — captures expert-driven exploration and additional edge ratings

**Storage decision:** Flask endpoint `/submit_evaluation` appends each completed comparison as a JSON entry to `evaluations/results.json` on the server (created automatically). Client-side JSON download also available as backup. No database introduced — plain JSON is sufficient for a single evaluator study and is easy to load into pandas for analysis.

**Re-use decision:** `eval.html` is a standalone full HTML page (not loaded via the SPA like `gallery.html`). This gives the evaluator a clean, focused interface without the full gallery UI. The graph rendering logic was re-implemented as a `GraphPanel` class (not imported from `gallery.js`) to keep the two panels fully independent and avoid DOM coupling.

---

## 51. Goal 10 Implementation — Evaluation UI

### Backend additions (app.py)

Two new routes added:

```python
@app.route('/eval')
def eval_page():
    # Login-gated. Serves eval.html with bagatelle_data JSON.

@app.route('/submit_evaluation', methods=['POST'])
def submit_evaluation():
    # Appends entry to evaluations/results.json.
    # Creates evaluations/ directory on first call.
    # Adds server_timestamp before saving.
```

The `/related` and `/retrieve` endpoints are reused unchanged — the eval panels call the same backend as the main gallery.

### Frontend (templates/eval.html)

Standalone HTML page with all CSS and JS inline (no external JS file). Key components:

**`GraphPanel` class** encapsulates all state and rendering for one panel:
- `nodes: Map`, `edges: Map`, `root`, `expansionCount`, `modesUsed`
- `fetchRelated(imagePath, excludePaths)` — calls `/related` with panel's mode/desc settings
- `addExpansion(selectedPath, relatedItems, selectedItem)` — same logic as `addGraphExpansion()` in gallery.js
- `render()` — builds graph-canvas div with SVG edges and absolutely-positioned node buttons. Node size: 110×130px (explicit `height: 130px` in CSS to match `NH=130` constant for edge alignment)
- `renderStats()` — writes nodes/edges/avg-score/variance/top-categories to panel stats bar
- `getStatsData()` — returns stats object included in submitted JSON

**Structured mode flow:**
1. `loadTask(index)` — updates task bar with seed artwork thumbnail and title
2. `loadBothPanels()` — calls `fetchRelated` on both panels in parallel (`Promise.all`), then `addExpansion` for each
3. After `submitRating()`, advances to next task automatically with 800ms delay

**Free mode flow:**
1. `freeSearch()` — calls `/retrieve`, renders thumbnails
2. Clicking a thumbnail calls `openFreeSelectLightbox(path)` — shows full-size image with "Pick this artwork" / "Choose different" buttons
3. `confirmFreeSelect()` → `loadFreeArtwork(path)` — clears both panels and loads in parallel

**Edge rating:**
- SVG edge hitbox (transparent 14px-wide path on top of visible edge) has click listener
- Click calls `openEdgeRatingPopup(edge, panel, clientX, clientY)` — positions popup near cursor
- Rating stored in `evalState.edgeRatings` array; panel re-rendered so edge colour updates immediately
  - `edge-rated-yes` → green stroke
  - `edge-rated-maybe` → amber dashed stroke
  - `edge-rated-no` → grey dotted stroke

**Node info popup:**
- ℹ button added to each graph node (position:absolute top-right, shown on hover)
- `showNodeInfo(node)` fills `#node-info-popup` with image, title, category, text_preview
- `<details>` element for full description created lazily on first call, reused on subsequent calls
- `text_full` is now stored in node data alongside `text_preview` in `addExpansion()`

**Rating panel:**
- Radio button groups for relevance / exploration / explanations (Left / Tie / Right)
- Visual "chosen" highlight via JS class toggle (CSS radio inputs hidden)
- `submitRating()` builds entry object, POSTs to `/submit_evaluation`, resets UI
- `downloadResults()` serialises `evalState` to Blob and triggers browser download

### Known CSS gotcha

`gallery_style.css` defines `.graph-node { width: 140px; min-height: 165px; }`. Including it in `eval.html` overrides the 110×130px eval node sizes, causing edge misalignment (edge centers computed from 110/130 constants but nodes render at 165px height). Fix: do not include `gallery_style.css` in eval.html — all needed styles are defined inline.

A second bug during development: adding `.graph-node { position: relative; }` as a separate CSS rule (to enable the info button's `position: absolute`) overrides the main rule's `position: absolute`, breaking all node placement. `position: absolute` already creates a containing block for child absolute elements — no `position: relative` needed.

---

## 52. Seed Artwork Selection — Rationale

16 artworks were selected to stress-test strategy divergence across the text vs image spectrum. Three evaluators (author + MD evaluator) use the same fixed seeds for comparability.

**Selection criteria:**
- Artworks where text strategy and image strategy would produce *different* neighbours
- Coverage across medical specialties and historical periods
- Mix of painting, sculpture, manuscript, and clinical illustration
- Some "control" cases where both strategies should agree

**Categorised by expected strategy divergence:**

| # | Title | Expected divergence |
|---|---|---|
| 1 | Japanese Smallpox Manuscript | Both strategies agree — explicit visual and textual signal |
| 2 | Dalton Rash of Sores (1856) | Both strategies agree — clinical illustration, disease visible |
| 3 | Mona Lisa (LDL diagnosis) | **Text >> Image** — portrait, no visible disease; image finds other portraits |
| 4 | Gentileschi Judith (goiter) | **Text >> Image** — goiter on maid barely visible; image finds Baroque drama |
| 5 | Caravaggio Sleeping Cupid | **Text >> Image** — hormonal reading entirely textual; image finds Baroque cherubs |
| 6 | Michelangelo Night (breast cancer) | **Text >> Image** — sculpture, retroactive diagnosis; image has no painting neighbours |
| 7 | Rembrandt Anatomy Lesson | Control — unambiguous medical scene, strategies should converge |
| 8 | Cholera Before/After (1831) | Both agree — clinical illustration format |
| 9 | Bruegel The Beggars (1568) | **Middle** — visible disabilities but symbolic; image finds genre scenes |
| 10 | Zumbo The Plague (17th C.) | **Image diverges** — wax sculpture unique in collection; image finds nothing similar |
| 11 | Fuseli The Nightmare (1781) | **Text >> Image** — psychiatric via text only; image finds Romantic/supernatural |
| 12 | Munch The Sick Child (1885) | **Text >> Image** — tuberculosis textual; image finds Expressionist emotion |
| 13 | Ribera The Club Foot (1642) | **Middle** — visible deformity but portrait composition dominates image strategy |
| 14 | Honthorst The Dentist (1622) | **Text >> Image** — dental via text; image finds Dutch Golden Age genre |
| 15 | Ancient Egyptian Medicine | **Image diverges** — papyrus painting visually unlike anything else |
| 16 | Tamerlane (disability) | **Text >> Image** — Persian court painting; disability invisible, known only historically |

Artworks 3, 4, 5, 6, 11, 12, 14, 16 are the strongest test cases for text strategy superiority. Artworks 7 and 8 serve as controls. Artworks 10 and 15 are edge cases for the image strategy (unique visual domains).
