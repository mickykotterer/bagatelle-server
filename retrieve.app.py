def retrieve():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No JSON payload received"}), 400

    # Selected LLM for refinement
    llm_model = data.get("llm")
    if llm_model and not session.get("logged_in"):
        return jsonify({"error": "Not logged in"}), 401

    # Search query
    question = data.get("question")

    # Number of images to retrieve
    try:
        top_k = int(data.get("k", 3))
    except (TypeError, ValueError):
        top_k = 3

    raw_weight = data.get("weight")
    try:
        weight = float(raw_weight)
    except ValueError:
        weight = 0

    image_paths = []
    if question:
        try:
            if weight > 0:
                if weight == 1:
                    logger.info("Text search")
                    image_paths = query_text_collection(question, top_k)
                else:
                    logger.info("Combined image and text search: ", weight)
                    image_paths = query_image_and_text_collection(question, top_k, weight, 1 - weight)
            else:
                logger.info("Image search")
                image_paths = query_image_collection(question, top_k)
            if llm_model:
                image_paths = refine_response(question, image_paths, llm_model)
            return jsonify({"response": image_paths})
        except Exception as e:
            print(e)
            return jsonify({"response": image_paths, "error": "Model failed to run!"})
    return jsonify({"response": image_paths, "error": "Invalid request!"})