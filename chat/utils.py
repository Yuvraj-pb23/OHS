import os
import pickle  # nosec B403
from io import BytesIO

import joblib
import matplotlib.pyplot as plt
import numpy as np
import requests
import torch
from PIL import Image
from sentence_transformers import SentenceTransformer, util
from sklearn.metrics.pairwise import cosine_similarity
import hmac
import hashlib
from django.conf import settings

class SecurityError(Exception):
    pass

# Hardcoded SHA-256 hashes of known safe models.
# This prevents malicious files from being loaded, even if uploaded to trusted directories.
TRUSTED_MODELS_SHA256 = {
    "chatbot_model.pkl": "34920314ee6b923ad150676123ba1d6076087257e490f88673c2d07490110fd2",
    "keyword_index.pkl": "41c92b90c738f3c6f97c03d419ef96381da990410a5f7b8e689f2a7c201ce264",
    "label_encoder.pkl": "21edfd402534924fe8a5e8660cb36be33a8b7e99e7ce5ad9affd27d3b14c7443",
    "semantic_data.pkl": "45c5135d5f0fcb57674de9c3110761245110eeb5132a4e57687eae9925156230",
}

def verify_file_signature(file_path):
    if not os.path.exists(file_path):
        return
        
    abs_path = os.path.abspath(file_path)
    try:
        base_dir = settings.BASE_DIR
    except Exception:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
    trusted_dir = os.path.abspath(os.path.join(base_dir, "chat", "data"))
    
    if not abs_path.startswith(trusted_dir):
        raise SecurityError(f"Model file {file_path} is not in a trusted directory ({trusted_dir})!")
        
    filename = os.path.basename(file_path)
    if filename not in TRUSTED_MODELS_SHA256:
        raise SecurityError(f"Unknown model file {filename}! Missing from trusted hashes.")
        
    expected_hash = TRUSTED_MODELS_SHA256[filename]
    
    with open(file_path, "rb") as f:
        computed_hash = hashlib.sha256(f.read()).hexdigest()
        
    if computed_hash != expected_hash:
        raise SecurityError(f"Integrity check failed for {file_path}! Unauthorized modification detected.")

# --- Image Chatbot Components (UPDATED) ---


class ImageChatbot:
    """
    Updated to support IRC button clicks that show image suggestions (up to 4 images per IRC).
    """

    def __init__(self, model_path="chat/data/image_chatbot_model.pkl"):
        self.model_data = None
        self.vectorizer = None
        self.data = None
        self.feature_matrix = None
        self.irc_index = None
        self.last_suggestions = []
        self.load_model(model_path)

    """
    Loads the trained chatbot model safely and verifies compatibility.
    Only trusted local pickle files are allowed.
    """

    def load_model(self, model_path):
        try:
            # Ensure file exists
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Model file not found: {model_path}")

            # Ensure file is local (prevent remote path injection)
            model_path = os.path.abspath(model_path)

            verify_file_signature(model_path)

            print(f"[Image Chatbot] Loading model from: {model_path}")

            # Load trusted local pickle model
            with open(model_path, "rb") as f:
                self.model_data = pickle.load(
                    f
                )  # nosec B301 (trusted local model file)

            # Extract required components
            self.vectorizer = self.model_data["vectorizer"]
            self.data = self.model_data["data"]
            self.feature_matrix = self.model_data["feature_matrix"]

            self.irc_index = self.model_data.get(
                "irc_index", {}
            )  # Example: {'irc82': ['fig1', 'fig2']}

            # Validate schema compatibility
            if "clean_name" not in self.data.columns:
                raise ValueError(
                    "Model is outdated. Please retrain with the updated script "
                    "to include 'clean_name'."
                )

            # Version metadata
            model_version = self.model_data.get("model_version", "Unknown")
            trained_at = self.model_data.get("trained_at", "Not specified")

            print(
                f"[Image Chatbot] Model loaded successfully! "
                f"Version: {model_version} (Trained at: {trained_at})"
            )

            # Display available IRC codes
            if self.irc_index:
                print(
                    "[Image Chatbot] Available IRC image codes:",
                    ", ".join(sorted(self.irc_index.keys())),
                )

            return True

        except Exception as e:
            print(f"[Image Chatbot] Failed to load model: {e}")
            return False

    def get_images_by_irc(self, irc_code, limit=4):
        """
        Get up to 'limit' images for a specific IRC code.
        Returns a list of formatted image results.
        """
        # --- CORRECTED SECTION ---
        # This section is now fixed to filter images based on the provided IRC code.

        # 1. Clean the input to match the keys in your model (e.g., "irc 82" -> "irc82")
        cleaned_irc_code = irc_code.replace(" ", "")

        # 2. Check if this IRC code exists in your image index
        if cleaned_irc_code in self.irc_index:
            # 3. Get the list of figure numbers associated with this IRC code
            fig_numbers_for_irc = self.irc_index[cleaned_irc_code]

            # 4. Filter your main data to get only the images for this specific IRC
            irc_specific_data = self.data[
                self.data["fig_number"].isin(fig_numbers_for_irc)
            ]

            if not irc_specific_data.empty:
                # 5. If there are more images than the limit, take a random sample from the correct group
                if len(irc_specific_data) > limit:
                    irc_specific_data = irc_specific_data.sample(limit)

                # 6. Format and return the SPECIFIC images
                images = [
                    self.format_row_as_result(row, 1.0)
                    for _, row in irc_specific_data.iterrows()
                ]
                return images

        # Return an empty list if the IRC code isn't found or has no images
        print(f"Warning: IRC code '{cleaned_irc_code}' not found in the image index.")
        return []
        # --- END OF CORRECTED SECTION ---

    def find_best_match(self, user_input):
        """
        Finds the best matching image and then returns a list of ALL images
        from that same figure section (e.g., all figures starting with "17.").
        The best match is always the first item in the returned list.
        """
        cleaned_input = user_input.lower().strip()
        best_match_row = None
        similarity_score = 1.0

        # 1. Find the single best match
        exact_fig_match = self.data[self.data["fig_number"] == cleaned_input]
        if not exact_fig_match.empty:
            print("✅ Found an exact figure number match!")
            best_match_row = exact_fig_match.iloc[0]
        else:
            exact_name_match = self.data[self.data["clean_name"] == cleaned_input]
            if not exact_name_match.empty:
                print("✅ Found an exact name match!")
                best_match_row = exact_name_match.iloc[0]
            else:
                print("No exact match found. Using similarity search...")
                query_vec = self.vectorizer.transform([cleaned_input])
                similarities = cosine_similarity(
                    query_vec, self.feature_matrix
                ).flatten()
                top_index = np.argmax(similarities)
                top_score = similarities[top_index]

                if top_score > 0.3:
                    print(f"✅ Found a close match with score: {top_score:.2f}")
                    best_match_row = self.data.iloc[top_index]
                    similarity_score = top_score

        # 2. If a match was found, find all its relatives
        if best_match_row is not None:
            primary_fig_number = best_match_row["fig_number"]

            # Extract the main section (e.g., "17" from "17.05")
            main_section = primary_fig_number.split(".")[0]

            # Find all rows in the dataframe that belong to the same section
            related_df = self.data[
                self.data["fig_number"].str.startswith(main_section + ".")
            ].copy()
            print(f"Found {len(related_df)} total images in section '{main_section}'.")

            # Format all found images into the result dictionary structure
            all_related_images = []
            for _, row in related_df.iterrows():
                # The primary match gets its real similarity score, others can be 1.0
                sim = (
                    similarity_score if row["fig_number"] == primary_fig_number else 1.0
                )
                all_related_images.append(self.format_row_as_result(row, sim))

            # Ensure the BEST match is the FIRST item in the list
            for i, img in enumerate(all_related_images):
                if img["fig_number"] == primary_fig_number:
                    all_related_images.insert(0, all_related_images.pop(i))
                    break

            return all_related_images

        # 3. If no match was found, return an empty list
        return []

    def format_row_as_result(self, row, similarity):
        """Formats a row of data into a structured result dictionary."""
        return {
            "name": row["name"],
            "fig_number": row["fig_number"],
            "image_url": row["image_url"],
            "similarity": similarity,
            "definition": row.get("define", "No definition available."),
        }

    def display_image(self, image_url):
        """Displays an image from a URL."""
        try:
            print(f"Displaying image from: {image_url}")
            response = requests.get(image_url, timeout=15)
            response.raise_for_status()
            image = Image.open(BytesIO(response.content))
            plt.figure(figsize=(10, 8))
            plt.imshow(image)
            plt.axis("off")
            plt.tight_layout()
            plt.show()
        except Exception as e:
            print(f"❌ Error displaying image: {str(e)}")

    def match_followup(self, user_input):
        """Match user input against previous suggestions (numbered selection)."""
        if user_input.strip().isdigit():
            index = int(user_input.strip()) - 1
            if 0 <= index < len(self.last_suggestions):
                item = self.last_suggestions[index]
                self.last_suggestions = []
                return item
        return None

    def predict_answer(self, user_input):
        """
        Main prediction function:
        - IRC button clicks (irc 67, irc 35, irc 82) → Show image suggestions
        - Regular image search → Direct image display
        """
        cleaned_input = user_input.strip().lower()

        # ===================================================
        # HANDLE IRC BUTTON CLICKS - Will be handled by unified handler
        # ===================================================
        if cleaned_input in ["irc 67", "irc67", "irc 35", "irc35", "irc 82", "irc82"]:
            return {"display_type": "irc_button", "irc_code": cleaned_input}

        # ===================================================
        # HANDLE NUMBERED SELECTION from suggestions
        # ===================================================
        followup_item = self.match_followup(user_input)
        if followup_item:
            return followup_item

        # ===================================================
        # HANDLE REGULAR IMAGE SEARCH
        # ===================================================
        results = self.find_best_match(user_input)

        if results:
            top_result = results[0]
            self.last_suggestions = results

            print("-" * 60)
            print(f"Best Match Found (1 of {len(results)} in this section):")
            print(f"  Name: {top_result['name']}")
            print(f"  Figure: {top_result['fig_number']}")
            print(f"  Definition: {top_result['definition']}")
            print(f"  Score: {top_result['similarity']:.3f}")
            print("-" * 60)

            return top_result
        else:
            return None

    def interactive_chat(self, text_chatbot):
        """
        Handles the interactive command-line session for image search.
        text_chatbot parameter is passed to handle unified IRC responses.
        """
        print("\n" + "=" * 60)
        print("🤖 Precise Image Chatbot - Ready to help!")
        print("=" * 60)
        print("💬 Ask for an image by its name, definition, or figure number.")
        print("   - Type 'IRC 67', 'IRC 35', or 'IRC 82' for image suggestions")
        print("   - Type 'back' to return to mode selection.")
        print("-" * 60)

        while True:
            try:
                user_input = input("\n🎯 You (Image): ").strip()
                if not user_input:
                    continue

                if user_input.lower() in ["back", "quit", "exit"]:
                    break

                print(f"\n🔍 Searching for: '{user_input}'")
                result = self.predict_answer(user_input)

                # Check if this is an IRC button click
                if (
                    isinstance(result, dict)
                    and result.get("display_type") == "irc_button"
                ):
                    irc_code = result["irc_code"].replace("irc ", "").replace("irc", "")

                    # Get both images and text suggestions
                    images = self.get_images_by_irc(irc_code, limit=4)
                    questions = text_chatbot.get_questions_by_type(f"irc{irc_code}")

                    if images or questions:
                        print(f"\n🤖 Bot: 📋 IRC {irc_code} - Combined Suggestions")
                        print("=" * 60)

                        combined_suggestions = []

                        # Display Images section
                        if images:
                            print(f"\n🖼️  IMAGES ({len(images)}):")
                            for i, img in enumerate(images, 1):
                                print(
                                    f"   {i}. {img['name']} (Fig: {img['fig_number']})"
                                )
                                combined_suggestions.append(("image", img))

                        # Display Questions section
                        if questions:
                            print(f"\n💬 QUESTIONS ({len(questions)}):")
                            for i, q in enumerate(questions, 1):
                                print(f"   {i + len(images)}. {q}")
                                combined_suggestions.append(("question", q))

                        print("=" * 60)
                        self.last_suggestions = combined_suggestions
                    else:
                        print(f"❌ No suggestions available for IRC {irc_code}.")

                elif isinstance(result, dict):
                    # Regular image result
                    print("\n🤖 Bot: Image found!")
                    self.display_image(result["image_url"])
                elif result:
                    print(f"\n🤖 Bot: {result}")
                else:
                    print("❌ No images found matching your query.")
                    print("💡 Try checking the spelling or using a different keyword.")

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ An unexpected error occurred: {str(e)}")


# --- Text Chatbot Components (No changes needed here) ---


class TextChatbot:
    def __init__(self, model_path, label_encoder_path, semantic_data_path):
        verify_file_signature(model_path)
        verify_file_signature(label_encoder_path)
        verify_file_signature(semantic_data_path)

        self.model = joblib.load(model_path)
        self.label_encoder = joblib.load(label_encoder_path)

        try:
            semantic_data = joblib.load(semantic_data_path)
            self.all_data = {
                "questions": semantic_data["questions"],
                "answers": semantic_data["answers"],
                "embeddings": torch.tensor(semantic_data["embeddings"]),
                "types": semantic_data["types"],
                "keywords": semantic_data["keywords"],
            }
        except KeyError:
            raise ValueError(
                "Model files are outdated! Please re-run your training script to include "
                "'types' and 'keywords' in 'semantic_data.pkl'."
            )

        self.semantic_model = SentenceTransformer("all-MiniLM-L6-v2")
        self.last_suggestions = []

        # Count questions by type for display
        type_counts = {}
        for t in self.all_data["types"]:
            type_counts[t] = type_counts.get(t, 0) + 1

        print("Text Chatbot Model loaded successfully!")
        print(f"  • IRC 67: {type_counts.get('irc67', 0)} questions")
        print(f"  • IRC 35: {type_counts.get('irc35', 0)} questions")
        print(f"  • IRC 82: {type_counts.get('irc82', 0)} questions")
        print(f"  • General: {type_counts.get('general', 0)} questions")
        print(
            f"  • Other: {sum(v for k, v in type_counts.items() if k not in ['irc67', 'irc35', 'irc82', 'general'])}"
        )

    def get_questions_by_type(self, type_name):
        """Get all questions of a specific type"""
        questions = []
        for i, t in enumerate(self.all_data["types"]):
            if t == type_name:
                questions.append(self.all_data["questions"][i])
        return questions

    def match_followup(self, user_input):
        """Match user input against previous suggestions"""
        if user_input.strip().isdigit():
            index = int(user_input.strip()) - 1
            if 0 <= index < len(self.last_suggestions):
                answer = self.last_suggestions[index][1]
                self.last_suggestions = []
                return answer
        for q, a in self.last_suggestions:
            if user_input.strip().lower() in q.lower():
                self.last_suggestions = []
                return a
        return None

    def get_semantic_match(self, user_question):
        """Find the best semantic match for any question"""
        user_embedding = self.semantic_model.encode(
            user_question, convert_to_tensor=True
        )
        cosine_scores = util.pytorch_cos_sim(
            user_embedding, self.all_data["embeddings"]
        )[0]
        top_score, top_index = torch.max(cosine_scores), torch.argmax(cosine_scores)
        return top_index.item(), top_score.item()

    def count_stored_keywords_in_question(self, question_text, stored_keywords):
        """
        Count how many DISTINCT stored keywords appear in the question text.
        Each keyword is counted only once (presence/absence), not by frequency.
        """
        if not stored_keywords:
            return 0

        question_lower = question_text.lower()
        keyword_presence_count = 0

        for keyword in stored_keywords:
            if keyword.lower() in question_lower:
                keyword_presence_count += 1

        return keyword_presence_count

    def get_semantic_match_with_keyword_ranking(self, user_question, threshold=0.60):
        """
        Find the best semantic match, but if multiple questions are above threshold,
        prioritize the one with FEWER stored keywords present (more specific match)
        """
        user_embedding = self.semantic_model.encode(
            user_question, convert_to_tensor=True
        )
        cosine_scores = util.pytorch_cos_sim(
            user_embedding, self.all_data["embeddings"]
        )[0]

        # Find all candidates above threshold
        candidates = []
        for idx, score in enumerate(cosine_scores):
            if score >= threshold:
                question_text = self.all_data["questions"][idx]
                stored_keywords = (
                    self.all_data["keywords"][idx]
                    if self.all_data["keywords"][idx]
                    else []
                )

                # Count how many stored keywords are present in this question
                keyword_count = self.count_stored_keywords_in_question(
                    question_text, stored_keywords
                )

                candidates.append(
                    {
                        "index": idx,
                        "score": score.item(),
                        "keyword_count": keyword_count,
                        "question": question_text,
                        "keywords": stored_keywords,
                    }
                )

        if candidates:
            # Sort by: 1) Higher score, 2) Lower keyword count (more specific)
            candidates.sort(key=lambda x: (-x["score"], x["keyword_count"]))

            best = candidates[0]
            print(f"📊 Found {len(candidates)} candidates above threshold")
            print(f"🎯 Selected: '{best['question']}'")
            print(
                f"   Score: {best['score']:.2f} | "
                f"Keywords in question: {best['keyword_count']} | "
                f"Stored keywords: {best['keywords']}"
            )

            return best["index"], best["score"]
        else:
            # No candidates above threshold, return the highest score
            top_score, top_index = torch.max(cosine_scores), torch.argmax(cosine_scores)
            return top_index.item(), top_score.item()

    def predict_answer(self, user_question, suggestion_threshold=0.60):
        """
        Main prediction function:
        - IRC button clicks → Show suggestions
        - Regular questions → Direct answers (with keyword-based ranking)
        """
        cleaned_input = user_question.strip().lower()

        # ===================================================
        # HANDLE IRC BUTTON CLICKS - Return suggestions ONLY
        # ===================================================
        if cleaned_input in ["irc 67", "irc67"]:
            questions = self.get_questions_by_type("irc67")
            if questions:
                print(
                    f"✅ IRC 67 button clicked. Showing {len(questions)} suggestions."
                )
                return {
                    "display_type": "button_selection",
                    "message": "📋 IRC 67 Questions - Select one:",
                    "options": questions,
                }
            else:
                return "❌ No IRC 67 questions available in the database."

        if cleaned_input in ["irc 35", "irc35"]:
            questions = self.get_questions_by_type("irc35")
            if questions:
                print(
                    f"✅ IRC 35 button clicked. Showing {len(questions)} suggestions."
                )
                return {
                    "display_type": "button_selection",
                    "message": "📋 IRC 35 Questions - Select one:",
                    "options": questions,
                }
            else:
                return "❌ No IRC 35 questions available in the database."

        if cleaned_input in ["irc 82", "irc82"]:
            questions = self.get_questions_by_type("irc82")
            if questions:
                print(
                    f"✅ IRC 82 button clicked. Showing {len(questions)} suggestions."
                )
                return {
                    "display_type": "button_selection",
                    "message": "📋 IRC 82 Questions - Select one:",
                    "options": questions,
                }
            else:
                return "❌ No IRC 82 questions available in the database."

        # ===================================================
        # HANDLE NUMBERED SELECTION from suggestions
        # ===================================================
        followup_answer = self.match_followup(user_question)
        if followup_answer:
            return followup_answer

        # ===================================================
        # HANDLE REGULAR QUESTIONS - Use keyword-based ranking
        # ===================================================
        top_index, top_score = self.get_semantic_match_with_keyword_ranking(
            user_question, suggestion_threshold
        )

        print(f"🔍 Match confidence: {top_score:.2%}")

        if top_score >= suggestion_threshold:
            # High confidence - Return matched answer DIRECTLY
            print(f"✅ High confidence match found (Score: {top_score:.2f}).")
            matched_answer = self.all_data["answers"][top_index]
            self.last_suggestions = []
            return matched_answer
        else:
            # Low confidence - offer suggestions
            print(f"⚠️ Low confidence (Score: {top_score:.2f}). Offering suggestions.")
            user_embedding = self.semantic_model.encode(
                user_question, convert_to_tensor=True
            )
            cosine_scores = util.pytorch_cos_sim(
                user_embedding, self.all_data["embeddings"]
            )[0]
            top_indices = torch.topk(
                cosine_scores, k=min(3, len(cosine_scores))
            ).indices.tolist()
            suggestions = [
                (self.all_data["questions"][i], self.all_data["answers"][i])
                for i in top_indices
            ]
            self.last_suggestions = suggestions
            options = "\n".join(
                [f"{i + 1}. {q}" for i, (q, _) in enumerate(suggestions)]
            )
            return (
                "We regret that your query falls outside OHPL scope; "
                "Our AI chatbot is continually improving to broaden its capabilities, "
                f"Did you mean one of these?\n\n{options}\n\n"
            )

    def interactive_chat(self):
        print("\n" + "=" * 60)
        print("🤖 Text Chatbot - Ready to help!")
        print("=" * 60)
        print("💬 Ask me anything about OHPL.")
        print("   - Type 'IRC 67', 'IRC 35', or 'IRC 82' for topic suggestions")
        print("   - Type 'back' to return to mode selection.")
        print("-" * 60)

        while True:
            try:
                user_input = input("\n🎯 You (Text): ").strip()
                if not user_input:
                    continue

                if user_input.lower() in ["back", "quit", "exit"]:
                    break

                response = self.predict_answer(user_input)

                # Handle dictionary responses (for button selections)
                if isinstance(response, dict):
                    print(f"\n🤖 Bot: {response['message']}")
                    for i, option in enumerate(response["options"], 1):
                        print(f"   {i}. {option}")
                else:
                    print(f"\n🤖 Bot: {response}")

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ An unexpected error occurred: {str(e)}")


# --- Main Application ---


def main():
    try:
        text_chatbot = TextChatbot(
            "chat/data/chatbot_model.pkl",
            "chat/data/label_encoder.pkl",
            "chat/data/semantic_data.pkl",
        )
        image_chatbot = ImageChatbot("chat/data/image_chatbot_model.pkl")

        while True:
            print("\n" + "=" * 60)
            print("👑 Welcome to the OHPL Unified Chatbot!")
            print("=" * 60)
            print("Choose a mode:")
            print("  1. 🖼️  Image Chatbot (Find images by name or figure number)")
            print("  2. 💬  Text Chatbot (Ask questions about OHPL)")
            print("  - Type 'quit' to exit.")
            print("-" * 60)

            choice = input("Enter your choice (1 or 2): ").strip()

            if choice == "1":
                image_chatbot.interactive_chat(text_chatbot)
            elif choice == "2":
                text_chatbot.interactive_chat()
            elif choice.lower() in ["quit", "exit"]:
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please enter 1 or 2.")

    except Exception as e:
        print(f"❌ Could not start the chatbot: {str(e)}")
