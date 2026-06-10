import glob
import csv
from pathlib import Path
from dotenv import load_dotenv
import os
# from api.openai_client import get_image_description_from_file

if not os.getenv("ANTHROPIC_API_KEY"):
    print("🔍 ANTHROPIC_API_KEY not found in environment — trying to load from .env")
    load_dotenv()

from api.anthropic_client import get_image_description_from_file


def create_image_descriptions():
    files = glob.glob('../static/data/images/*.*')
    existing_images = [str(p) for p in files]

    def load_file_map(file_name):
        files = []
        with open(file_name, 'r') as csv_file:
            reader = csv.reader(csv_file, delimiter=',')
            next(reader, None)
            for row in reader:
                files.append({"file": row[0], "caption": row[1]})
        file_map = {}
        for obj in files:
            stem = Path(obj["file"]).stem
            file_map[stem] = obj
        return file_map

    file_name = os.path.join('./data', 'artwork_names_filtered.csv')
    file_map = load_file_map(file_name)

    output_csv = "./data/image_descriptions.csv"

    with open(output_csv, "w", encoding="utf8", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(["file_name", "description"])  # header row

        for i, path in enumerate(existing_images, start=1):
            if i > 2:
                break
            stem = Path(path).stem
            if stem in file_map:
                image_file = file_map[stem]["file"]
                caption = file_map[stem]["caption"]
                print(i, image_file, caption)

                question = (
                    "Describe this image\n"
                    f"File name: {image_file}\n"
                    f"Caption: {caption}"
                )
                description = get_image_description_from_file(
                    path, question, "claude-sonnet-4-20250514"
                )
                writer.writerow([image_file, description])

if __name__ == "__main__":
    create_image_descriptions()
