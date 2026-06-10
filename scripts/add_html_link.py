import pandas as pd
import os

# Input and output file paths
input_csv = "file_list.csv"
output_csv = "file_list_html.csv"

# Read the CSV file
df = pd.read_csv(input_csv)

# Check if required columns exist
if "Filename" not in df.columns or "Classification" not in df.columns:
    raise ValueError("CSV must contain 'FileName' and 'Classification' columns.")

# Create a new column 'HTML_link' by replacing the extension with .html
df["HTML_link"] = df["Filename"].apply(lambda f: os.path.splitext(f)[0] + ".html")

# Save to a new CSV file
df.to_csv(output_csv, index=False)

print(f"✅ Processed file saved as: {output_csv}")
