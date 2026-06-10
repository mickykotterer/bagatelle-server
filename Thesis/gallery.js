import {initializeMagniview} from './magniview/main.js';

// Filter images by selected categories
function updateImages() {
    const selectedCategories = Array.from(
        document.querySelectorAll('#checkbox-container input[type="checkbox"]:checked')
    ).map((checkbox) => checkbox.value);

    const filteredImages = (selectedCategories.length > 0) ? images.filter((image) =>
        selectedCategories.includes(image.category)
    ) : [...images];
    displayImages(filteredImages);
    clearSelected();
}

async function fetchRelatedArtworks(imagePath, excludePaths = []) {
    const selectedLlm = document.querySelector('input[name="llm_model"]:checked')?.value
        || document.querySelector('input[name="llm_refine_choice"]:checked')?.value
        || "claude-sonnet-4";

    const graphMode = document.getElementById("graph-mode")?.value || "text_clip";

    const response = await fetch("/related", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            image_path: imagePath,
            k: 3,
            exclude_paths: excludePaths,
            llm: selectedLlm,
            mode: graphMode,
        }),
    });

    const data = await response.json();

    if (!response.ok) {
        console.error("Related artwork request failed:", data);
        return null;
    }

    console.log("Related artworks:", data);
    return data;
}


function renderRelatedArtworks(relatedItems) {
    const container = document.getElementById("related-results");
    const status = document.getElementById("related-status");

    if (!container) {
        console.error("Could not find #related-results container");
        return;
    }

    container.innerHTML = "";

    if (!relatedItems || relatedItems.length === 0) {
        if (status) {
            status.textContent = "No related artworks found.";
        }
        return;
    }

    if (status) {
        status.textContent = "Click a related artwork to keep exploring.";
    }

    relatedItems.forEach((item) => {
        const path = item.image_path;
        const titleText = item.title || getFileName(path);
        const score = item.score;
        const textPreview = item.text_preview || "";
        const textFull = item.text_full || textPreview;

        const card = document.createElement("article");
        card.classList.add("related-card");

        const img = document.createElement("img");
        img.src = "/" + path;
        img.classList.add("related-card-image");
        img.title = getFileName(path);

        img.addEventListener("click", async () => {
            if (status) {
                status.textContent = "Finding related artworks...";
            }

            const data = await fetchRelatedArtworks(path, getGraphExclusionPaths(path));

            if (data) {
                addGraphExpansion(data.selected.image_path, data.related, data.selected);
                renderRelatedArtworks(data.related);
            }
        });

        const title = document.createElement("div");
        title.classList.add("related-card-title");
        title.textContent = titleText;

        const scoreEl = document.createElement("div");
        scoreEl.classList.add("related-card-score");
        scoreEl.textContent = `Similarity score: ${score}`;

        const explanation = document.createElement("p");
        explanation.classList.add("related-card-explanation");
        explanation.textContent = item.edge_explanation || "";

        const preview = document.createElement("p");
        preview.classList.add("related-card-preview");
        preview.textContent = textPreview;

        const details = document.createElement("details");
        details.classList.add("related-card-details");

        const summary = document.createElement("summary");
        summary.textContent = "Show full description";

        const fullText = document.createElement("p");
        fullText.classList.add("related-card-fulltext");
        fullText.textContent = textFull;

        details.appendChild(summary);
        details.appendChild(fullText);

        card.appendChild(img);
        card.appendChild(title);
        card.appendChild(scoreEl);
        if (item.edge_explanation) {
            card.appendChild(explanation);
        }
        card.appendChild(preview);
        card.appendChild(details);

        container.appendChild(card);
    });
}

// Update visual block with selected images
function updateSelected(selectedImages, updateCheckboxes = true) {
    const selectedContainer = document.getElementById("selected-image-container");
    selectedContainer.innerHTML = "";

    [...selectedImages].forEach(fileName => {
        const src = getImagePath(fileName);
        const link = fileName.replace(/\.[^/.]+$/, ".html");
        let thumbnailFigure = createThumbnailFigure(src, fileName, link);
        selectedContainer.appendChild(thumbnailFigure);

        //Sync checkboxes
        if (updateCheckboxes) {
            const chbName = getCheckboxName(src);
            const checkboxes = document.querySelectorAll(`input[type="checkbox"][name=${chbName}`);
            checkboxes.forEach(c => c.checked = true);
        }
    });
    const selectedToolbar = document.getElementById('selected-toolbar');
    if ([...selectedImages].length > 0){
        selectedToolbar.style.display = 'flex';
    } else {
        selectedToolbar.style.display = 'none';
    }
}

// Create a relative path given a file name
function getImagePath(fileName) {
    return "./static/data/images/" + fileName;
}

function getHTMLPath(fileName){
    return "./static/data/html_claude-sonnet-4/" + fileName.replace(/\.[^/.]+$/, ".html");
}

// Get file name from relative or full path
function getFileName(src) {
    const parts = src.split(/[\\/]/);
    return parts[parts.length - 1];
}

function addGraphExpansion(selectedPath, relatedItems, selectedItem = null) {
    if (!selectedPath || !relatedItems) {
        return;
    }

    if (!graphRoot) {
        graphRoot = selectedPath;
    }

    let selectedDepth = 0;

    if (!graphNodes.has(selectedPath)) {
        graphNodes.set(selectedPath, {
            id: selectedPath,
            image_path: selectedPath,
            label: selectedItem?.title || getFileName(selectedPath),
            visits: 1,
            depth: 0
        });
    } else {
        const existing = graphNodes.get(selectedPath);
        existing.visits += 1;
        selectedDepth = existing.depth || 0;

        if (selectedItem?.title) {
            existing.label = selectedItem.title;
        }
    }

    relatedItems.forEach((item, index) => {
        const relatedPath = item.image_path;

        if (!relatedPath) {
            return;
        }

        const relatedDepth = selectedDepth + 1;

        if (!graphNodes.has(relatedPath)) {
            graphNodes.set(relatedPath, {
                id: relatedPath,
                image_path: relatedPath,
                label: item.title || getFileName(relatedPath),
                score: item.score,
                visits: 0,
                depth: relatedDepth,
                parent: selectedPath,
                siblingIndex: index
            });
        } else {
            const existing = graphNodes.get(relatedPath);

            if (item.title) {
                existing.label = item.title;
            }

            existing.depth = Math.min(existing.depth || relatedDepth, relatedDepth);

            if (!existing.parent) {
                existing.parent = selectedPath;
            }
        }

        const edgeId = `${selectedPath}|||${relatedPath}`;

        if (!graphEdges.has(edgeId)) {
            graphEdges.set(edgeId, {
                source: selectedPath,
                target: relatedPath,
                score: item.score,
                explanation: item.edge_explanation || ""
            });
        }
    });
    console.log("Graph nodes:", Array.from(graphNodes.values()));
    renderGraph();
}


function renderGraph() {
    const graphView = document.getElementById("graph-view");
    const graphStatus = document.getElementById("graph-status");

    if (!graphView) {
        console.error("Could not find #graph-view");
        return;
    }

    graphView.innerHTML = "";

    const nodes = Array.from(graphNodes.values());
    const edges = Array.from(graphEdges.values());

    if (nodes.length === 0) {
        if (graphStatus) {
            graphStatus.textContent = "Click an artwork to start building the exploration graph.";
        }
        return;
    }

    if (graphStatus) {
        graphStatus.textContent = `${nodes.length} nodes, ${edges.length} edges. Click any graph node to keep exploring.`;
    }

    const nodeWidth = 140;
    const nodeHeight = 165;
    const columnGap = 260;
    const rowGap = 45;
    const marginX = 100;
    const marginY = 80;

    const nodesByDepth = new Map();

    nodes.forEach((node) => {
        const depth = node.depth || 0;

        if (!nodesByDepth.has(depth)) {
            nodesByDepth.set(depth, []);
        }

        nodesByDepth.get(depth).push(node);
    });

    const depths = Array.from(nodesByDepth.keys()).sort((a, b) => a - b);
    const maxDepth = Math.max(...depths);

    let maxColumnSize = 1;

    nodesByDepth.forEach((depthNodes) => {
        maxColumnSize = Math.max(maxColumnSize, depthNodes.length);
    });

    const width = Math.max(900, marginX * 2 + maxDepth * columnGap + nodeWidth);
    const height = Math.max(
        560,
        marginY * 2 + maxColumnSize * (nodeHeight + rowGap)
    );

    const positions = new Map();

    depths.forEach((depth) => {
        const depthNodes = nodesByDepth.get(depth);

        // Sort nodes so the layout is stable.
        depthNodes.sort((a, b) => {
            if ((a.parent || "") !== (b.parent || "")) {
                return (a.parent || "").localeCompare(b.parent || "");
            }

            return a.label.localeCompare(b.label);
        });

        const columnHeight = depthNodes.length * nodeHeight + (depthNodes.length - 1) * rowGap;
        const startY = Math.max(marginY, (height - columnHeight) / 2);

        depthNodes.forEach((node, index) => {
            const x = marginX + depth * columnGap;
            const y = startY + index * (nodeHeight + rowGap);

            positions.set(node.id, {
                x,
                y
            });
        });
    });

    const graphCanvas = document.createElement("div");
    graphCanvas.classList.add("graph-canvas");
    graphCanvas.style.width = `${width}px`;
    graphCanvas.style.height = `${height}px`;

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("graph-edges");
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);

    edges.forEach((edge) => {
        const sourcePos = positions.get(edge.source);
        const targetPos = positions.get(edge.target);

        if (!sourcePos || !targetPos) {
            return;
        }

        const sourceX = sourcePos.x + nodeWidth / 2;
        const sourceY = sourcePos.y + nodeHeight / 2;
        const targetX = targetPos.x + nodeWidth / 2;
        const targetY = targetPos.y + nodeHeight / 2;

        const midX = (sourceX + targetX) / 2;

        const d = `
            M ${sourceX} ${sourceY}
            C ${midX} ${sourceY},
            ${midX} ${targetY},
            ${targetX} ${targetY}
        `;

        // Visible edge
        const visiblePath = document.createElementNS("http://www.w3.org/2000/svg", "path");
        visiblePath.setAttribute("d", d);
        visiblePath.classList.add("graph-edge");
        svg.appendChild(visiblePath);

        // Invisible thick hover target
        const hitboxPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
        hitboxPath.setAttribute("d", d);
        hitboxPath.classList.add("graph-edge-hitbox");

        const edgeTitle = document.createElementNS("http://www.w3.org/2000/svg", "title");

        if (edge.explanation) {
            edgeTitle.textContent = `Similarity score: ${edge.score}\n\n${edge.explanation}`;
        } else {
            edgeTitle.textContent = `Similarity score: ${edge.score}`;
        }

        hitboxPath.appendChild(edgeTitle);

        svg.appendChild(hitboxPath);

        const labelX = (sourceX + targetX) / 2;
        const labelY = (sourceY + targetY) / 2;

        const labelGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
        labelGroup.classList.add("graph-edge-label-group");

        const labelBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        labelBg.classList.add("graph-edge-label-bg");
        labelBg.setAttribute("x", labelX - 18);
        labelBg.setAttribute("y", labelY - 9);
        labelBg.setAttribute("width", 36);
        labelBg.setAttribute("height", 18);
        labelBg.setAttribute("rx", 8);

        const labelText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        labelText.classList.add("graph-edge-label");
        labelText.setAttribute("x", labelX);
        labelText.setAttribute("y", labelY);
        labelText.textContent = edge.score !== undefined ? Number(edge.score).toFixed(2) : "";

        labelGroup.appendChild(labelBg);
        labelGroup.appendChild(labelText);

        svg.appendChild(labelGroup);
    });

    graphCanvas.appendChild(svg);

    nodes.forEach((node) => {
        const pos = positions.get(node.id);

        const nodeEl = document.createElement("button");
        nodeEl.classList.add("graph-node");

        if (node.id === graphRoot) {
            nodeEl.classList.add("graph-node-root");
        }

        nodeEl.style.left = `${pos.x}px`;
        nodeEl.style.top = `${pos.y}px`;
        nodeEl.title = node.label;

        const img = document.createElement("img");
        img.src = "/" + node.image_path;
        img.alt = node.label;

        const label = document.createElement("span");
        label.textContent = node.label;

        nodeEl.appendChild(img);
        nodeEl.appendChild(label);

        nodeEl.addEventListener("click", async () => {
            const status = document.getElementById("related-status");

            if (status) {
                status.textContent = "Finding related artworks...";
            }

            const data = await fetchRelatedArtworks(
                node.image_path,
                getGraphExclusionPaths(node.image_path)
            );

            if (data) {
                addGraphExpansion(data.selected.image_path, data.related, data.selected);
                renderRelatedArtworks(data.related);
            }
        });

        graphCanvas.appendChild(nodeEl);
    });

    graphView.appendChild(graphCanvas);
}

function clearGraph() {
    graphNodes.clear();
    graphEdges.clear();
    graphRoot = null;

    const graphView = document.getElementById("graph-view");
    const graphStatus = document.getElementById("graph-status");

    if (graphView) {
        graphView.innerHTML = "";
    }

    if (graphStatus) {
        graphStatus.textContent = "Click an artwork to start building the exploration graph.";
    }
}


function getGraphExclusionPaths(selectedPath) {
    return Array.from(graphNodes.keys()).filter((path) => path !== selectedPath);
}

// Get checkbox name to locate relevant checkboxes per image file
function getCheckboxName(src) {
    return "chb_" + getFileName(src).replace(/[^a-zA-Z0-9]/g, "_");
}

// Create a link for image caption
function createLink(folder, filename, label) {
    let link = document.createElement("a");
    link.href = folder + filename;
    link.target = "_blank";
    link.innerText = label;
    return link;
}

// Create a figure to show image and associated information
function createThumbnailFigure(src, label, link) {
    const maxLength = 30;
    const thumbnail = document.createElement("img");
    thumbnail.src = src;
    thumbnail.classList.add("thumbnail");
    thumbnail.title = getFileName(src);

    thumbnail.style.cursor = "pointer";

    thumbnail.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();

        const status = document.getElementById("related-status");
        if (status) {
            status.textContent = "Finding related artworks...";
        }

        const cleanPath = src.replace(/^\.?\//, "");

        const data = await fetchRelatedArtworks(cleanPath, getGraphExclusionPaths(cleanPath));

        if (data) {
            addGraphExpansion(data.selected.image_path, data.related, data.selected);
            renderRelatedArtworks(data.related);
        }
    });
    //Figure
    const thumbnailFigure = document.createElement("figure")
    const thumbnailCaption = document.createElement("figcaption")

    const linksContainer = document.createElement("div");
    linksContainer.classList.add("linkColumn");
    linksContainer.appendChild(createLink("./static/data/html_claude-sonnet-4/", link, "Claude-sonnet-4"));
    linksContainer.appendChild(createLink("./static/data/html_gpt-4o/", link, "GPT-4o"));
    linksContainer.appendChild(createLink("./static/data/html_gpt-5/", link, "GPT-5"));

    const labelElem = document.createElement("div");
    labelElem.innerText = label.length > maxLength ? label.slice(0, maxLength - 1) + "…" : label;
    labelElem.classList.add("imageLabel");

    thumbnailCaption.appendChild(labelElem);
    thumbnailCaption.appendChild(linksContainer);

    thumbnailFigure.appendChild(thumbnail);
    thumbnailFigure.appendChild(thumbnailCaption);
    thumbnailFigure.setAttribute("data-magniview", "bagatelle");

    //Checkbox
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.classList.add(`imageCheckbox`)
    checkbox.name = getCheckboxName(src);
    thumbnailFigure.appendChild(checkbox);
    checkbox.addEventListener('change', toggleImageSelection);

    checkbox.checked = selectedImages.has(getFileName(src));

    return thumbnailFigure;
}

// Add/remove image from selected list on checkbox toggle
function toggleImageSelection(event) {
    event.preventDefault();
    const checkbox = event.target;
    const src = checkbox.parentElement.querySelector('img').src;
    const fileName = getFileName(src)

    const isChecked = checkbox.checked;
    if (isChecked) {
        selectedImages.add(fileName);
    } else {
        selectedImages.delete(fileName);
    }
    const chbName = getCheckboxName(src);
    const checkboxes = document.querySelectorAll(`input[type="checkbox"][name=${chbName}`);
    checkboxes.forEach(c => c.checked = isChecked);
    updateSelected(selectedImages, false);
}

// Load images into catalogue
function displayImages(images) {
    const imageContainer = document.getElementById("image-container");
    imageContainer.innerHTML = "";
    images.forEach((image, index) => {
        let label = `Image ${index + 1}`
        if (image.category) {
            label += `(${categoryAcronyms[image.category]})`;
        }
        let thumbnailFigure = createThumbnailFigure(
            'static/data/images/' + image.name, label, image.link);
        imageContainer.appendChild(thumbnailFigure);
    });
    try {
        initializeMagniview();
    } catch (e) {
        console.warn("Magniview re-initialization failed:", e);
    }
}

// Toggle rado group for LLM refined search
function updateLlmRadios(e) {
    let enabled = e.target.checked;
    // Prefer a wrapper element if present
    const wrapper = document.getElementById('llm-options');
    if (wrapper) {
        const radios = wrapper.querySelectorAll('input[type="radio"]');
        radios.forEach(r => {
            r.disabled = !enabled;
            if (!enabled) r.checked = false;
        });
        if (radios.length > 0 && enabled) {
            radios[0].checked = true;
        }
    }
}

// Populate category selection panel
function loadCategories() {
    let prevNum = 0;
    let prevLetter = "";
    categories.forEach(category => {
        let a = category[0]
        if (a === prevLetter) {
            prevNum += 1;
        } else {
            prevLetter = a;
            prevNum = 1;
        }
        categoryAcronyms[category] = a + prevNum;
    });
    const checkboxContainer = document.getElementById("checkbox-container");
    categories.forEach(category => {
        const label = document.createElement("label");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = category;
        label.appendChild(checkbox);
        const count = images.filter(image => image.category === category).length;
        label.appendChild(document.createTextNode(category + " (" + categoryAcronyms[category] + ") - " + count));
        checkboxContainer.appendChild(label);
        checkboxContainer.appendChild(document.createElement("br"));
    });
}

// Add message to the chat box
function addMessageToRagChat(sender, message) {
    const chatBox = document.getElementById("rag-chat-box");
    const messageElement = document.createElement("div");
    messageElement.classList.add("message");
    messageElement.classList.add(`${sender}-message`);
    messageElement.textContent = message;
    chatBox.appendChild(messageElement);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function sliderControl(ev){
  const sliderValue = document.getElementById('sliderValue');
  const parsedFloatEl = document.getElementById('parsedFloat');
  const intRepEl = document.getElementById('intRep');

  const raw = ev.target.value;
  sliderValue.textContent = raw;
  const v = parseFloat(raw);
  parsedFloatEl.textContent = v.toFixed(1);
  intRepEl.textContent = Math.round(v * 10);
}

// Submit password to get access to gallery
async function login() {
    const passwordInput = document.getElementById("password");
    const errorMsg = document.getElementById("error-msg");
    const loginContainer = document.getElementById("login-container");

    const password = passwordInput.value;

    try {
        const response = await fetch("/login", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({password})
        });

        const result = await response.json();
        console.log(result);
        if (result.success) {
            loginContainer.style.display = "none";
        } else {
            errorMsg.textContent = result.error || "Login failed";
        }

    } catch (err) {
        errorMsg.textContent = "Server error";
        console.error(err);
    }
}

// Submit request to the server to retrieve images
async function submitSearchRequest(ev) {
    ev.preventDefault();

    clearGraph();

    const relatedContainer = document.getElementById("related-results");
    const relatedStatus = document.getElementById("related-status");

    if (relatedContainer) {
        relatedContainer.innerHTML = "";
    }

    if (relatedStatus) {
        relatedStatus.textContent = "";
    }
    // Search query
    const question = document.getElementById('query-input').value.trim();
    if (!question) {
        alert("Please enter a question.");
        return;
    }

    // Top K images to extract
    let k = parseInt(document.getElementById('k-input').value, 10);
    if (Number.isNaN(k)) k = 1;
    k = Math.max(1, Math.min(10, k));
    // LLM version to cross-check image relevance
    let llmModel = null
    const llmOptions = document.querySelector('input[name="llm_refine_choice"]:checked');
    if (llmOptions) {
        llmModel = document.querySelector('input[name="llm_refine_choice"]:checked').value;
    }
    // Weight of visual vs textual data for search
    const rawWeight = document.getElementById('slider').value;

    // Display loading status
    retrieveStatus.textContent = `Retrieving top ${k} images...`;
    const btn = document.getElementById('retrieve-btn');
    btn.disabled = true;

    try {
        // POST JSON payload to server endpoint. Change URL if backend expects a different path.
        const resp = await fetch('/retrieve', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({question: question, k: k, llm: llmModel, weight: rawWeight})
        });

        if (!resp.ok) {
            throw new Error(`Server returned ${resp.status} ${resp.statusText}`);
        }

        const response = await resp.json();
        const data = response["response"];
        if (!Array.isArray(data)) {
            throw new Error('Server response is not a JSON array of image URLs/paths.');
        }

        // selectedImages = new Set(data.map(x => getFileName(x)));
        data.forEach(item => {
            const fname = getFileName(item);
            selectedImages.add(fname);
        });
        updateSelected(selectedImages);

        retrieveStatus.textContent = `Retrieved ${data.length} images.`;
    } catch (err) {
        console.error(err);
        retrieveStatus.textContent = `Error retrieving images: ${err.message || err}`;
        alert("Failed to retrieve images. See console for details.");
    } finally {
        btn.disabled = false;
    }
}

function setWorkshopFormDisabled(disabled) {
    const form = document.getElementById('workshop-form');
    if (!form) return;
    const controls = form.querySelectorAll('input, select, textarea, button');
    controls.forEach(el => el.disabled = disabled);
}

// Workshop form submission: collect params + selected images and call server LLM
async function submitWorkshopForm(ev) {
    ev.preventDefault();
    const statusEl = document.getElementById('workshop-status');

    const numDaysInput = document.getElementById('num-days');
    const themeInput = document.getElementById('theme');
    const audienceInput = document.getElementById('audience');

    const num_days = Math.max(1, Math.min(30, parseInt(numDaysInput.value || 3, 10)));
    const theme = (themeInput.value || "").trim();
    const audience = (audienceInput.value || "").trim();
    const llm_model = document.querySelector('input[name="llm_model"]:checked').value;

    if (!theme) {
        alert("Please provide a theme for the workshop.");
        return;
    }
    if (!audience) {
        alert("Please provide a target audience.");
        return;
    }

    // const llm_model = document.querySelector('input[name="llm_model"]:checked').value;
    const imagesArray = [...selectedImages]
    if (imagesArray.length === 0) {
        if (!confirm("No images selected. Generate programme without images?")) {
            return;
        }
    }

    if (imagesArray.length > 6) {
        alert("Please reduce the number of images, the service can process up to 6 images in one call.");
        return;
    }

    // const context_type = document.querySelector('input[name="context"]:checked').value;
    const context_type="write-ups"; 

    const context = context_type === "images"? [...selectedImages].map(x => getImagePath(x)).join('\n')
        : [...selectedImages].map(x => getHTMLPath(x)).join('\n')

    statusEl.textContent = "Generating programme — please wait...";
    const content = document.getElementById('workshop-result-content');
    setWorkshopFormDisabled(true);

    try {
        const resp = await fetch("/generate_program", {
            method: "POST",
            headers: {"Content-Type": "application/json", "Accept": "application/json"},
            body: JSON.stringify({
                num_days: num_days,
                theme: theme,
                audience: audience,
                context_type: context_type,
                context: context,
                llm: llm_model
            })
        });

        if (!resp.ok) {
            const txt = await resp.text();
            throw new Error(`Server returned ${resp.status}: ${txt}`);
        }

        const data = await resp.json();
        const programText = data["response"] || JSON.stringify(data);
        const prompt = data["prompt"] || "?"

        statusEl.textContent = "Programme generated.";
        showWorkshopProgram(programText, prompt);
    } catch (err) {
        console.error(err);
        statusEl.textContent = `Error: ${err.message || err}`;
        content.innerHTML = "";
        alert("Failed to generate programme. See console for details.");
        // Re-enable the form so the user can retry
        setWorkshopFormDisabled(false);
    }
}

// Call this after receiving `programText` from the server
function showWorkshopProgram(responseText, prompt) {
    const wToolbar = document.getElementById('workshop-result-toolbar');
    const wContent = document.getElementById('workshop-result-content');
    const wDownloadBtn = document.getElementById('workshop-download');
    const wClearBtn = document.getElementById('workshop-clear');
    const wPromptDownloadBtn = document.getElementById('prompt-download');

    if (!wContent) {
        console.error('showWorkshopProgram: element #workshop-result-content not found in DOM. Make sure gallery HTML is inserted and initialization ran after insertion.');
        return;
    }

    function extractHTML(responseText) {
      const htmlMatch = responseText.match(/```html\n?([\s\S]*?)```/i);
      if (htmlMatch) {
        return htmlMatch[1].trim();
      }
      return responseText.trim();
    }

    let htmlBody = extractHTML(responseText);

    if (!htmlBody || htmlBody.trim().length === 0) {
        wToolbar.style.display = 'none';
        wContent.innerHTML = "";
        // Nothing to show; re-enable the form so user can try again
        setWorkshopFormDisabled(false);
        return;
    }

    wContent.innerHTML = htmlBody;

    // Show toolbar and wire the download button
    wToolbar.style.display = 'flex';

    // Prepare an HTML file for download when the button is clicked
    wDownloadBtn.onclick = () => {
        const filename = `workshop_program_${new Date().toISOString().replace(/[:.]/g, "-")}.html`;
        const blob = new Blob([htmlBody], { type: "text/html" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    };

    if (wPromptDownloadBtn) {
        wPromptDownloadBtn.onclick = () => {
            const filename = `prompt_${new Date().toISOString().replace(/[:.]/g, "-")}.txt`;
            const blob = new Blob([prompt], { type: "text/txt" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        };
    }

    wClearBtn.onclick = () => {
         wContent.innerHTML = "";
         wToolbar.style.display = 'none';
         const themeInput = document.getElementById('theme');
         themeInput.value = "";
         const audienceInput = document.getElementById('audience');
         audienceInput.value = "";
         // Re-enable the workshop form after clearing the result
         setWorkshopFormDisabled(false);
         const statusEl = document.getElementById('workshop-status');
         if (statusEl) statusEl.textContent = "";
    };
}

function clearSelected(){
     [...selectedImages].forEach(fileName => {
        const src = getImagePath(fileName);
        const chbName = getCheckboxName(src);
        const checkboxes = document.querySelectorAll(`input[type="checkbox"][name=${chbName}`);
        checkboxes.forEach(c => c.checked = false);
    });
    selectedImages = new Set();
    const selectedContainer = document.getElementById("selected-image-container");
    selectedContainer.innerHTML = "";
    const selectedToolbar = document.getElementById('selected-toolbar');
    selectedToolbar.style.display = 'none';
}

// Global definitions and controls

const retrieveStatus = document.getElementById('retrieve-status');
const categories = Array.from(new Set(images.map(img => img["category"]))).sort();
const categoryAcronyms = {};
let selectedImages = new Set();

const graphNodes = new Map();
const graphEdges = new Map();
let graphRoot = null;

document.getElementById('llm-checkbox').addEventListener('change', updateLlmRadios);
document.getElementById("update-button").addEventListener("click", updateImages);
document.getElementById('retrieve-form').addEventListener('submit', submitSearchRequest);
document.getElementById('slider').addEventListener('input', sliderControl);
document.getElementById('workshop-form').addEventListener('submit', submitWorkshopForm);
document.getElementById('selected-clear').onclick = clearSelected;
document.getElementById('graph-clear').addEventListener('click', clearGraph);
// document.getElementById("rag-chat-form").addEventListener("submit", submitLLMQuestion);

const settingContainer = document.getElementById("settings-container");
settingContainer.style.marginRight = "20px";
settingContainer.style.minWidth = "300px";

// Initial setup
loadCategories();
displayImages(images);

