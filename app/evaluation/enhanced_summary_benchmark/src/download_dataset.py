import json
from datasets import load_dataset

# 1. CONFIGURATION
# ----------------
# Change this to the HuggingFace dataset you want to download
HF_DATASET_NAME = "stevendevoe/news-article-summary" 
SPLIT = "train"  # 'train', 'validation', or 'test'
LIMIT = 99     # How many articles to download (set to None for all)

# Map the HuggingFace columns to your desired keys
# Key = Your desired output key
# Value = The column name in the HuggingFace dataset
COLUMN_MAPPING = {
    "article": "article",      # 'text' is usually the body in slovak-sum
    "reference_summary": "summary" # 'summary' is the summary
}

def clean_text(text):
    """
    Helper to escape triple quotes if they exist in the text 
    to prevent syntax errors in the generated Python file.
    """
    if text is None:
        return ""
    # Escape backslashes first
    text = text.replace("\\", "\\\\")
    # Escape triple quotes by breaking them up
    text = text.replace('"""', '\"\"\"')
    return text.strip()

def main():
    print(f"Downloading {HF_DATASET_NAME}...")
    try:
        dataset = load_dataset(HF_DATASET_NAME, split=SPLIT)
    except Exception as e:
        print(f"Error loading dataset: {e}")
        return

    # Slice the dataset if a limit is set
    if LIMIT:
        dataset = dataset.select(range(LIMIT))

    output_filename = "dataset.py"

    print(f"Formatting and writing to {output_filename}...")
    
    with open(output_filename, "w", encoding="utf-8") as f:
        # Write the start of the list
        f.write("GOLD_STANDARD_DATASET = [\n")

        for i, row in enumerate(dataset):
            # Generate ID and Topic dynamically based on loop index
            # Example: article_01, article_02...
            article_id = f"article_{i+1:02d}"
            topic_id = str(i + 1)

            # Extract content based on mapping
            article_content = clean_text(row.get(COLUMN_MAPPING["article"], ""))
            summary_content = clean_text(row.get(COLUMN_MAPPING["reference_summary"], ""))

            # Format the entry as a Python dictionary string
            entry_str = f"""    {{
        "id": "{article_id}",
        "topic": "{topic_id}",
        "article": \"\"\"{article_content}\"\"\",
        "reference_summary": \"\"\"{summary_content}\"\"\",
    }},"""
            
            # Write the entry to file
            f.write(entry_str + "\n")

        # Write the end of the list
        f.write("]\n")

    print(f"Done! Check {output_filename}.")

if __name__ == "__main__":
    main()