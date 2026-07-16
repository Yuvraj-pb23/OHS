import json
import logging
import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .llm_engine import LLMEngine
from .rag_chatbot import RagChatbot

logger = logging.getLogger(__name__)

# -----------------------------
# Configuration
# -----------------------------
RESET_KEYWORDS = ["bye", "clear", "clear all", "goodbye", "quit", "exit"]
# -----------------------------
# Mock Models
# -----------------------------
class MockImageChatbot:
    def __init__(self, model_path=None):
        pass

    def get_images_by_irc(self, irc, limit=4):
        return [
            {
                "name": "Sample Image 1",
                "fig_number": "1.1",
                "image_url": "/static/images/RA-logo-1.png",
                "definition": "Sample definition for " + str(irc),
                "similarity": 1.0,
            }
        ]

    def find_best_match(self, query):
        return [
            {
                "name": f"Result for {query}",
                "fig_number": "1.1",
                "image_url": "/static/images/RA-logo-1.png",
                "definition": "This is a dummy result because models are missing.",
                "similarity": 0.95,
            }
        ]





# -----------------------------
# Lazy Load Models (Mock or Real)
# -----------------------------
image_chatbot = None
text_chatbot = None
rag_chatbot = None
_models_loaded = False

def load_real_models():
    global image_chatbot, text_chatbot, rag_chatbot, _models_loaded
    if _models_loaded:
        return
    try:
        from .utils import ImageChatbot, TextChatbot
        print("Lazy-loading real models...")

        image_model_path = os.path.join(settings.BASE_DIR, "chat", "data", "image_chatbot_model.pkl")
        if os.path.exists(image_model_path):
            image_chatbot = ImageChatbot(model_path=image_model_path)

        text_model_path = os.path.join(settings.BASE_DIR, "chat", "data", "chatbot_model.pkl")
        if os.path.exists(text_model_path):
            text_chatbot = TextChatbot(
                model_path=text_model_path,
                label_encoder_path=os.path.join(settings.BASE_DIR, "chat", "data", "label_encoder.pkl"),
                semantic_data_path=os.path.join(settings.BASE_DIR, "chat", "data", "semantic_data.pkl"),
            )

        # Initialize RAG Chatbot
        rag_index_path = os.path.join(settings.BASE_DIR, "chat/data/bot.index")
        rag_answers_path = os.path.join(settings.BASE_DIR, "chat/data/answers.json")
        if os.path.exists(rag_index_path) and os.path.exists(rag_answers_path):
            rag_chatbot = RagChatbot(rag_index_path, rag_answers_path)
        else:
            logger.warning(f"RAG Chatbot files not found at {rag_index_path} or {rag_answers_path}")

    except (ImportError, Exception) as e:
        logger.warning(f"Model loading failed or dependencies missing: {e}")
        image_chatbot = None
        text_chatbot = None

    if image_chatbot is None:
        image_chatbot = MockImageChatbot()

        
    _models_loaded = True


# -----------------------------
# Views
# -----------------------------


def index(request):
    return render(request, "chat/index.html")


def format_images_for_response(image_results):
    if not image_results:
        return []

    return [
        {
            "name": img.get("name", ""),
            "fig_number": img.get("fig_number", ""),
            "image_url": img.get("image_url", ""),
            "definition": img.get("definition", ""),
            "similarity": float(img.get("similarity", 1.0)),
        }
        for img in image_results
    ]


# -----------------------------
# Helper: Load POSH Data
# -----------------------------
# -----------------------------
# Helper: Load Topic Data
# -----------------------------
def load_topic_data(topic_name):
    """
    Load JSON data for a specific topic.
    topic_name: 'posh', 'posco', 'ic', 'mental_health'
    """
    filename_map = {
        "posh": "posh_question_answer.json",
        "posco": "posco_question_answer.json",
        "ic": "ic_question_answer.json",
        "mental_health": "mental_health_question_answer.json",
    }

    if topic_name not in filename_map:
        return {}

    try:
        json_path = os.path.join(settings.BASE_DIR, "chat", "data", filename_map[topic_name])
        # Fallback to current directory if BASE_DIR/json fails
        if not os.path.exists(json_path):
            json_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data",
                filename_map[topic_name],
            )

        if not os.path.exists(json_path):
            logger.debug(f"JSON file not found for {topic_name} at {json_path}")
            return {}

        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading JSON for {topic_name}: {e}")
        return {}


def get_subtopics_by_type(topic_name):
    data = load_topic_data(topic_name)
    if not data or "subtopics" not in data:
        return []
    return [st["title"] for st in data["subtopics"]]


def normalize_text(text):
    """Normalize text for comparison by removing special chars and lowering."""
    import re

    # Keep only alphanumeric and spaces, lower case
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()


SUPPORTED_TOPICS = ["posh", "posco", "ic", "mental_health"]


def get_questions_for_subtopic(subtopic_title):
    logger.debug(f"Searching for subtopic: '{subtopic_title}'")
    target = normalize_text(subtopic_title)

    for topic in SUPPORTED_TOPICS:
        data = load_topic_data(topic)
        if not data or "subtopics" not in data:
            continue

        for st in data["subtopics"]:
            current = normalize_text(st["title"])
            # Check for exact match or if one is contained in another (for partial matches)
            if target == current or target in current or current in target:
                logger.debug(f"Match found in {topic}: '{st['title']}'")
                return [q["question"] for q in st["questions"]]

    logger.debug("No matching subtopic found.")
    return []


def get_answer_for_question(question_text):
    logger.debug(f"Searching for answer to: '{question_text}'")
    target = normalize_text(question_text)

    for topic in SUPPORTED_TOPICS:
        data = load_topic_data(topic)
        if not data or "subtopics" not in data:
            continue

        for st in data["subtopics"]:
            for q in st["questions"]:
                current = normalize_text(q["question"])
                if target == current:
                    logger.debug(f"Answer found in {topic} for '{q['question']}'")
                    return q["answer"]

    logger.debug("No answer found in JSON.")
    return None

# FIX #3: Added per-session rate limiting (20 requests/min) and input length cap
def chatbot_response(request):
    load_real_models()
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    # FIX #3: Per-session rate limit — max 20 messages per minute
    from django.core.cache import cache
    import time
    session_key = request.session.session_key
    if not session_key:
        try:
            request.session.create()
            session_key = request.session.session_key
        except Exception:
            session_key = str(request.user.id) if request.user.is_authenticated else "anonymous"
    rl_key = f"chat_rl_{session_key}"
    rl_data = cache.get(rl_key, {"count": 0, "reset_at": time.time() + 60})
    if time.time() > rl_data["reset_at"]:
        rl_data = {"count": 1, "reset_at": time.time() + 60}
    else:
        rl_data["count"] += 1
    cache.set(rl_key, rl_data, timeout=60)
    if rl_data["count"] > 20:
        return JsonResponse({"error": "Too many requests. Please wait a moment before continuing."}, status=429)

    try:
        data = json.loads(request.body)
        # FIX #3: Cap input length to prevent DoS via oversized payloads
        user_question = data.get("message", "").strip()[:500]
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not user_question:
        return JsonResponse({"error": "Empty message"}, status=400)

    question_lower = user_question.lower()

    # Reset Logic
    if any(k in question_lower for k in RESET_KEYWORDS):
        return JsonResponse(
            {
                "response": "Goodbye! Feel free to ask me another question anytime.",
                "reset": True,
            }
        )

    # 1. Handle Top-Level Categories (POSH, POSCO, etc.) - PRIORITY CHECK
    irc_map = {
        "irc 67": "irc67",
        "irc67": "irc67",
        "irc 35": "irc35",
        "irc35": "irc35",
        "irc 82": "irc82",
        "irc82": "irc82",
        "ic": "ic",
        "posh": "posh",
        "posco": "posco",
        "mental health": "mental_health",
    }

    if question_lower in irc_map:
        irc_type = irc_map[question_lower]

        # Generalized handling for all topics (POSH, POSCO, IC, Mental Health)
        # to use JSON data if available
        if irc_type in SUPPORTED_TOPICS:
            subtopics = get_subtopics_by_type(irc_type)

            if subtopics:
                return JsonResponse(
                    {
                        "response": {
                            "message": f"Select a category for {irc_type.replace('_', ' ').upper()}:",
                            "options": subtopics,
                            "type": "subtopics_list",  # Explicit Type
                            "topic": irc_type,
                        }
                    }
                )

        # ... (Rest of existing logic for other types) ...
        irc_name = irc_type.replace("irc", "IRC ")
        images = []
        questions = []
        if image_chatbot:
            images = format_images_for_response(
                image_chatbot.get_images_by_irc(irc_type, limit=4)
            )
        if text_chatbot:
            questions = text_chatbot.get_questions_by_type(irc_type) or []

        return JsonResponse(
            {
                "response": {
                    "message": f"Here are the details for {irc_name}:",
                    "images": images,
                    "options": questions,
                    "type": "subtopics_list",  # Defaulting others to subtopics list style
                }
            }
        )

    # 2. Check if it's a known Subtopic -> Return Questions
    subtopic_questions = get_questions_for_subtopic(user_question)
    if subtopic_questions:
        return JsonResponse(
            {
                "response": {
                    "message": f"Please select a question related to '{user_question}':",
                    "options": subtopic_questions,
                    "type": "questions_list",  # Explicit Type
                    "parent_topic": "posh",  # Context for back button
                }
            }
        )

    # 3. Check if it's a known Question -> Return Answer
    direct_answer = get_answer_for_question(user_question)
    if direct_answer:
        return JsonResponse(
            {"response": {"message": direct_answer, "type": "answer"}}  # Explicit Type
        )

    # Check authentication for custom questions (RAG/LLM)
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "response": {
                    "message": "Please log in to your account to ask custom compliance questions.",
                    "type": "answer",
                }
            }
        )

    # 4. Check RAG Chatbot (New Faiss Integration)
    if rag_chatbot:
        rag_answer = rag_chatbot.get_answer(user_question)
        if rag_answer:
            return JsonResponse({"response": {"message": rag_answer, "type": "answer"}})

    # 5. Integrate LLM (RAG)
    # If no direct match in JSON, ask the LLM
    logger.debug(f"Asking LLM for '{user_question}'")
    llm_engine = LLMEngine.get_instance()
    # Only query LLM if it's ready or we want to try initializing it
    llm_response = llm_engine.generate_answer(user_question)

    if (
        llm_response
        and "answering using context" not in llm_response.lower()
        and "model is not ready" not in llm_response.lower()
    ):
        return JsonResponse({"response": {"message": llm_response, "type": "answer"}})
    # If LLM fails or is not ready, fall through to old logic
    if "Model is not ready" in llm_response:
        logger.debug(f"LLM not ready: {llm_response}")

    # ... (Rest of existing logic for images/fallback) ...
    if image_chatbot:
        image_results = image_chatbot.find_best_match(user_question)
        if image_results:
            return JsonResponse(
                {
                    "response": {
                        "message": "I found these relevant images:",
                        "images": format_images_for_response(image_results),
                    }
                }
            )

    if text_chatbot:
        # Fallback for hardcoded answers (POSCO, etc.) if not in JSON
        # This handles the POSCO/IC/Mental Health subtopics -> Dummy answers flow
        # defined in MockTextChatbot.predict_answer
        return JsonResponse({"response": text_chatbot.predict_answer(user_question)})

    return JsonResponse(
        {"response": "Chatbot service is currently unavailable."}, status=500
    )
