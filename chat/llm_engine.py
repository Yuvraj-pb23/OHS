import json
import os
import pickle  # nosec B403
import warnings

import numpy as np
import torch
from django.conf import settings
from .utils import verify_file_signature

warnings.filterwarnings("ignore")


class LLMEngine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.embedder = None
        self.index = None
        self.metadata = None
        self.tokenizer = None
        self.model = None
        self.is_ready = False
        self.error_message = None

        self._load_resources()

    # -------------------------------------------------
    # Build FAISS index if missing
    # -------------------------------------------------
    def build_index_from_json(self, json_path, index_path, meta_path):
        print(f"[LLM Engine] Building index from {json_path}...")

        try:
            import faiss
            from sentence_transformers import SentenceTransformer

            if self.embedder is None:
                print("[LLM Engine] Loading embedder for indexing...")
                self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            documents = []

            for item in data:
                text = (
                    f"Instruction: {item.get('instruction', '')}\n"
                    f"Input: {item.get('input', '')}\n"
                    f"Output: {item.get('output', '')}"
                )
                documents.append(text)

            print(f"[LLM Engine] Encoding {len(documents)} documents...")
            embeddings = self.embedder.encode(documents)

            dimension = embeddings.shape[1]
            index = faiss.IndexFlatL2(dimension)
            index.add(np.array(embeddings).astype("float32"))

            print(f"[LLM Engine] Saving index to {index_path}...")
            faiss.write_index(index, index_path)

            print(f"[LLM Engine] Saving metadata to {meta_path}...")
            with open(meta_path, "wb") as f:
                pickle.dump(documents, f)

            print("[LLM Engine] Index build complete.")
            return True

        except Exception as e:
            print(f"[LLM Engine] Error building index: {e}")
            return False

    # -------------------------------------------------
    # Load model resources
    # -------------------------------------------------
    def _load_resources(self):
        try:
            print("[LLM Engine] Loading resources...")

            import faiss
            from peft import PeftModel
            from sentence_transformers import SentenceTransformer
            from transformers import AutoModelForCausalLM, AutoTokenizer

            # Paths
            oshllm_dir = os.path.join(settings.BASE_DIR, "oshllm")

            if not os.path.exists(oshllm_dir):
                oshllm_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "oshllm",
                )

            index_path = os.path.join(oshllm_dir, "faiss.index")
            meta_path = os.path.join(oshllm_dir, "meta.pkl")
            json_path = os.path.join(oshllm_dir, "doc.json")
            model_path = os.path.join(oshllm_dir, "qwen_instruct", "checkpoint-60")

            base_model_name = "gpt2"

            # Build index if missing
            if not os.path.exists(index_path) or not os.path.exists(meta_path):
                print("[LLM Engine] Index or metadata missing.")

                if os.path.exists(json_path):
                    success = self.build_index_from_json(
                        json_path, index_path, meta_path
                    )

                    if not success:
                        raise FileNotFoundError("Failed to build index from doc.json")
                else:
                    raise FileNotFoundError(f"doc.json not found at {json_path}")

            # Load embedder
            if self.embedder is None:
                print("[LLM Engine] Loading embedder...")
                self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

            # Load FAISS index
            print("[LLM Engine] Loading FAISS index...")
            self.index = faiss.read_index(index_path)

            # Load metadata safely (trusted file)
            print("[LLM Engine] Loading metadata...")
            verify_file_signature(meta_path)
            with open(meta_path, "rb") as f:
                self.metadata = pickle.load(f)  # nosec B301

            # Detect device
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"[LLM Engine] Using device: {device}")

            # Load tokenizer
            print("[LLM Engine] Loading tokenizer...")

            self.tokenizer = AutoTokenizer.from_pretrained(
                base_model_name,
                revision="6c0e6080953db56375760c0471a8c5f2929f6e9b",
                trust_remote_code=False,
            )

            print("[LLM Engine] Loading base model...")

            self.model = AutoModelForCausalLM.from_pretrained(
                base_model_name,
                revision="6c0e6080953db56375760c0471a8c5f2929f6e9b",
                trust_remote_code=False,
                torch_dtype=torch.float32,
            )

            # Load LoRA adapter if available
            if os.path.exists(model_path):
                print(f"[LLM Engine] Loading LoRA adapter from {model_path}...")

                try:
                    self.model = PeftModel.from_pretrained(
                        self.model, model_path, is_trainable=False
                    )

                except Exception as e:
                    print(f"[LLM Engine] Adapter load failed: {e}. Using base model.")

            else:
                print(
                    f"[LLM Engine] Adapter not found at {model_path}. Using base model."
                )

            self.model.eval()
            self.is_ready = True

            print("[LLM Engine] Initialization complete.")

        except Exception as e:
            print(f"[LLM Engine] Error initializing: {e}")
            self.error_message = str(e)
            self.is_ready = False

    # -------------------------------------------------
    # Retrieve context from FAISS
    # -------------------------------------------------
    def retrieve(self, query, k=2):

        if not self.is_ready or not self.embedder or not self.index:
            return []

        q_emb = self.embedder.encode([query])
        _, idx = self.index.search(q_emb, k)

        return [self.metadata[i] for i in idx[0] if i < len(self.metadata)]

    # -------------------------------------------------
    # Generate answer using RAG
    # -------------------------------------------------
    def generate_answer(self, query):

        if not self.is_ready:
            return (
                f"AI Model is not ready. Error: "
                f"{self.error_message or 'Unknown error'}"
            )

        try:
            context = self.retrieve(query, k=1)
            context_str = "\n".join(context)

            prompt = f"""You are a workplace compliance assistant.
Answer ONLY using the context below.
If the answer is not present, say "Information not available."

Context:
{context_str}

Question:
{query}

Answer:
"""

            inputs = self.tokenizer(prompt, return_tensors="pt")

            with torch.no_grad():
                out = self.model.generate(
                    **inputs,
                    max_new_tokens=150,
                    temperature=0.7,
                    top_p=0.9,
                    do_sample=True,
                    repetition_penalty=1.2,
                    no_repeat_ngram_size=3,
                )

            if "gpt2" in self.tokenizer.name_or_path:
                retrieved_text = (
                    context[0] if context else "Information not available in doc.json."
                )

                if "Output:" in retrieved_text:
                    return retrieved_text.split("Output:")[-1].strip()

                return retrieved_text

            decoded = self.tokenizer.decode(out[0], skip_special_tokens=True)

            if "Answer:" in decoded:
                return decoded.split("Answer:")[-1].strip()

            return decoded.strip()

        except Exception as e:
            return f"Error generating answer: {e}"
