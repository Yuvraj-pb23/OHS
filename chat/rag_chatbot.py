try:
    import faiss
except ImportError:
    faiss = None

import json
import numpy as np
import os
from sentence_transformers import SentenceTransformer

class RagChatbot:
    """
    RAG Chatbot using Faiss and SentenceTransformer.
    Loads a pre-computed Faiss index and an answers JSON file.
    """
    def __init__(self, index_path, answers_path, model_name="all-MiniLM-L6-v2"):
        self.index_path = index_path
        self.answers_path = answers_path
        self.model_name = model_name
        self.model = None
        self.index = None
        self.answers = None
        self.is_ready = False

        self.load_resources()

    def load_resources(self):
        try:
            print(f"Loading RAG model: {self.model_name}...")
            self.model = SentenceTransformer(self.model_name)
            
            print(f"Loading Faiss index from {self.index_path}...")
            if not os.path.exists(self.index_path):
                raise FileNotFoundError(f"Index file not found at {self.index_path}")
            self.index = faiss.read_index(self.index_path)

            print(f"Loading answers from {self.answers_path}...")
            if not os.path.exists(self.answers_path):
                raise FileNotFoundError(f"Answers file not found at {self.answers_path}")
            
            with open(self.answers_path, "r", encoding="utf-8") as f:
                self.answers = json.load(f)
            
            self.is_ready = True
            print("RAG Chatbot loaded successfully.")

        except Exception as e:
            print(f"Error loading RAG Chatbot resources: {e}")
            self.is_ready = False

    def get_answer(self, query):
        """
        Retrieves the best matching answer for the given query.
        """
        if not self.is_ready:
            return None

        try:
            # Convert to embedding
            query_embedding = self.model.encode([query])

            # Search Faiss index
            # k=1 means we want the single best match
            D, I = self.index.search(np.array(query_embedding), k=1)

            best_match_index = I[0][0]
            
            # Use string key if answers is a dict with string keys (common in JSON), 
            # or integer index if it's a list.
            # Based on 'another approach', it seemed to use direct indexing `answers[best_match]`.
            # We should handle potential key errors or index errors.
            
            # Check if answers is a list or dict
            if isinstance(self.answers, list):
                if 0 <= best_match_index < len(self.answers):
                     return self.answers[best_match_index]
            elif isinstance(self.answers, dict):
                 # faiss returns integer IDs. If JSON keys are strings of ints, convert.
                 str_index = str(best_match_index)
                 if str_index in self.answers:
                     return self.answers[str_index]
            
            print(f"Warning: Match index {best_match_index} not found in answers.")
            return None

        except Exception as e:
            print(f"Error during RAG search: {e}")
            return None
