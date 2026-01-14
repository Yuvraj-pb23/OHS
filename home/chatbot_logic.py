# Handles chatbot response
import joblib
import os
from sentence_transformers import SentenceTransformer, util
import torch

# === Load saved components ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load SVM classifier and label encoder
model = joblib.load(os.path.join(BASE_DIR, "chatbot_model.pkl"))
label_encoder = joblib.load(os.path.join(BASE_DIR, "label_encoder.pkl"))

# Load semantic data (questions, answers, embeddings)
semantic_data = joblib.load(os.path.join(BASE_DIR, "semantic_data.pkl"))
questions = semantic_data["questions"]
answers = semantic_data["answers"]
embeddings = torch.tensor(semantic_data["embeddings"])  # Convert to tensor

# Load sentence transformer model
semantic_model = SentenceTransformer('all-MiniLM-L6-v2')

# === Hybrid Predict Function ===


# === Fallback memory for suggested questions ===
last_suggestions = []

# === Match user input to previous suggestions ===
def match_followup(user_input):
    global last_suggestions

    # 1. Handle numeric replies like "1", "2", or "3"
    if user_input.strip().isdigit():
        index = int(user_input.strip()) - 1
        if 0 <= index < len(last_suggestions):
            answer = last_suggestions[index][1]
            last_suggestions = []  # Clear suggestions
            return answer

    # 2. Handle text-based matches
    for q, a in last_suggestions:
        if user_input.strip().lower() in q.lower():
            last_suggestions = []  # Clear suggestions
            return a

    return None

# === Suggest top N similar questions ===
def get_question_suggestions(user_question, top_n=3):
    user_embedding = semantic_model.encode(user_question, convert_to_tensor=True)
    cosine_scores = util.pytorch_cos_sim(user_embedding, embeddings)[0]
    top_indices = torch.topk(cosine_scores, k=top_n).indices.tolist()
    return [(questions[i], answers[i]) for i in top_indices], float(torch.max(cosine_scores))

# === Hybrid Predict Function with fallback ===
def predict_answer(user_question, threshold=0.5):
    global last_suggestions

    # Step 1: Check if input is a follow-up to suggestions
    followup = match_followup(user_question)
    if followup:
        return followup

    # Step 2: Semantic similarity search
    suggestions, top_score = get_question_suggestions(user_question)

    if top_score >= threshold:
        last_suggestions = []
        return suggestions[0][1]
    else:
        last_suggestions = suggestions
        options = "\n".join([f"{i+1}. {q}" for i, (q, _) in enumerate(suggestions)])
        return (
            f"Apologies I could not understand \"{user_question}\" since it is not related to OHS,\n"
            f"Did you mean one of these?\n\n{options}\n\n" 
        )