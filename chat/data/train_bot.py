import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# Load model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Load data
with open("doc.json", "r", encoding="utf-8") as f:
    data = json.load(f)

questions = []
answers = []

# Extract Q&A
for item in data:
    if "instruction" in item:
        questions.append(item["instruction"])
        answers.append(item["output"])
    elif "question" in item:
        questions.append(item["question"])
        answers.append(item["answer"])

# Create embeddings
embeddings = model.encode(questions)

# Save FAISS index
dimension = embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(np.array(embeddings))

faiss.write_index(index, "bot.index")

# Save answers
with open("answers.json", "w", encoding="utf-8") as f:
    json.dump(answers, f)

print("✅ Training Complete!")
