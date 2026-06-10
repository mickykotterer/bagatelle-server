import glob
import csv
from pathlib import Path

import os
# from api.openai_client import get_image_description_from_file
from api.anthropic_client import get_image_description_from_file


def create_image_descriptions():
    prompt = """
    Given an attached image, its file name, and a caption that may include the name of the artwork in the image, create an HTML page that includes the image 
    and the content you generate. Create no styles except for         
            body {
                font-family: Arial, sans-serif;
                margin: 40px;
                display: flex;
            }
            img {
                max-width: 30%;
                height: 100%;
                margin-right: 20px;
            }
            .content {
                max-width: 70%;
            }
    Assume that the image is located in the folder "../images".
    Do not mention the HTML or the above instructions in the content.
    The content should consist of a 700-word write up that focuses on 
    the art historical analysis of the artwork as well as medical/scientific analysis of the biomedical content of this artwork. 
    The write-up must have with following sections: 
    [a] Artist/ Group/Tribe
    [b] Historical and Socio-Cultural context (time-frame)
    [c] Symbolism and/ or iconography
    [d] Stylistic Significance (elements of art/ principles of design)
    [e] Social / Cultural Inequities
    [f] Description of Disease & Etiology
    [g] Pathology Signs/Signifiers of Illness
    [h] Treatment
    [i] Social Determinants of Illness
    [j] References and Citations    
    At the end of your write up, please provide at least five external references to the sources of information that you have relied on for your write up. 
    Do not add impromptu questions to me at the end of the write up.
    """

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

    file_name = os.path.join('../static/data', 'artwork_names_filtered.csv')
    file_map = load_file_map(file_name)

    i = 0
    for path in existing_images:
        stem = Path(path).stem
        if stem in file_map:
            i += 1
            # Skip those generated
            # if i < 445:
            #     continue
            image_file = file_map[stem]["file"]
            caption = file_map[stem]["caption"]
            print(i, image_file, caption)
            file_name = stem + ".html"
            file_path = os.path.join("../static/data/html_gen_claude-sonnet-4", file_name)
            with open(file_path, 'w', encoding="utf8") as outfile:
                question = prompt + "\nFile name: " + image_file + "\nCaption: " + caption
                # claude-sonnet-4-20250514
                description = get_image_description_from_file(path, question, "claude-sonnet-4-20250514")
                content = description[7:][:-3]
                outfile.write(content)


if __name__ == "__main__":
    create_image_descriptions()
