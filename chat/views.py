import json
import os

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .llm_engine import LLMEngine
from .rag_chatbot import RagChatbot

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


class MockTextChatbot:
    def __init__(self, *args, **kwargs):
        pass

    def get_questions_by_type(self, type_name):
        if type_name == "posh":
            return [
                "Definitions & Scope",
                "The Internal Committee (IC)",
                "Filing a Complaint",
                "Inquiry & Procedure",
                "Conciliation & Settlement",
                "Recommendations & Action",
                "Employer Obligations",
                'Scenario-Based "Grey Areas"',
            ]
        elif type_name == "posco":
            return [
                "Legal Core & Definitions",
                "Mandatory Reporting (Sec 19)",
                "Aggravated Offences",
                "Child Pornography & Digital",
                "Investigation Procedures",
                "Medical Examination",
                "Special Courts & Trial",
                "Institutional Safeguards",
            ]
        elif type_name == "ic":
            return [
                "Composition & Legal Status",
                "The External Member",
                "Pre-Inquiry Procedures",
                "Principles of Natural Justice",
                "Evidence & Documentation",
                "The Inquiry Report",
                "Punishments & Remedies",
                "Post-Inquiry & Compliance",
            ]
        elif type_name == "mental_health":
            return [
                "Mental Health Literacy",
                "Legal Rights & Compliance",
                "Psychological Safety",
                "Managerial Responsibilities",
                "Work-Life Integration",
                "Stigma & Language",
                "Crisis Intervention",
                "Scenario-Based Challenges",
            ]
        return ["What is the standard width for lanes?", "How to install signs?"]

    def predict_answer(self, query):
        # Dummy answers for POSH, POSCO, IC, Mental Health subtopics
        all_answers = {
            # --- POSH ---
            "definitions & scope": (
                "POSH Act covers sexual harassment at workplace. "
                "It defines 'aggrieved woman', 'workplace', and 'sexual harassment'."
            ),
            "the internal committee (ic)": (
                "Every employer of a workplace must constitute an Internal Committee (IC) "
                "if there are 10 or more employees."
            ),
            "filing a complaint": (
                "An aggrieved woman can file a complaint in writing to the IC "
                "within 3 months from the date of the incident."
            ),
            "inquiry & procedure": (
                "The IC must complete the inquiry within 90 days. "
                "Both parties must be given a fair opportunity to be heard."
            ),
            "conciliation & settlement": (
                "Before initiating inquiry, the IC may, at the request of the aggrieved woman, "
                "take steps to settle the matter through conciliation."
            ),
            "recommendations & action": (
                "On completion of inquiry, the IC provides a report. "
                "If allegations are proved, it recommends action against the respondent."
            ),
            "employer obligations": (
                "Employers must provide a safe working environment, "
                "display penal consequences of sexual harassment, and organize workshops."
            ),
            'scenario-based "grey areas"': (
                "Grey areas include consensual relationships turned sour, "
                "harassment outside office hours but impactful on work, etc."
            ),
            # --- POSCO ---
            "legal core & definitions": (
                "POSCO Act 2012 provides protection to children from offenses of "
                "sexual assault, sexual harassment and pornography."
            ),
            "mandatory reporting (sec 19)": (
                "Section 19 mandates reporting of sexual offenses against children "
                "to the Special Juvenile Police Unit or local police."
            ),
            "aggravated offences": (
                "Aggravated penetrative sexual assault includes offenses by persons in authority "
                "(police, armed forces, public servants) and carries stricter punishment."
            ),
            "child pornography & digital": (
                "Using children for pornographic purposes or storing such material "
                "is a serious offense under POSCO."
            ),
            "investigation procedures": (
                "Investigation must be conducted by a child-friendly officer, not in uniform, "
                "and the child should not be detained at the police station."
            ),
            "medical examination": (
                "Medical examination of the child must be conducted in the presence of "
                "parents/guardians and by a female doctor if possible."
            ),
            "special courts & trial": (
                "Special Courts are designated for speedy trial of POSCO cases. "
                "The trial should be completed within one year."
            ),
            "institutional safeguards": (
                "Requires child care institutions, schools, and hostels to have "
                "guidelines and mechanisms to prevent abuse."
            ),
            # --- IC ---
            "composition & legal status": (
                "IC must have a Presiding Officer (senior woman), 2 employee members "
                "committed to women's cause/legal knowledge, and 1 external member."
            ),
            "the external member": (
                "External Member must be from an NGO or association committed to the cause of "
                "women or a person familiar with issues relating to sexual harassment."
            ),
            "pre-inquiry procedures": (
                "IC meets to review the complaint, ensures copies are given to the respondent "
                "within 7 days, and checks limitation period."
            ),
            "principles of natural justice": (
                "Both parties have right to be heard. No bias. Cross-examination is allowed "
                "dependent on IC discretion."
            ),
            "evidence & documentation": (
                "IC follows civil court powers for summoning witnesses, discovering documents. "
                "Confidentiality is key."
            ),
            "the inquiry report": (
                "Report must include findings and recommendations. Must be submitted to "
                "employer within 10 days of completion."
            ),
            "punishments & remedies": (
                "Punishments range from written apology, withholding promotion/increment, "
                "to termination. Compensation can be deducted from salary."
            ),
            "post-inquiry & compliance": (
                "Employer must act on recommendations within 60 days. "
                "Annual Report inclusion is mandatory."
            ),
            # --- Mental Health ---
            "mental health literacy": (
                "Understanding signs of stress, burnout, anxiety, and depression "
                "in the workplace context."
            ),
            "legal rights & compliance": (
                "Mental Healthcare Act 2017 ensures right to equality and non-discrimination "
                "for persons with mental illness."
            ),
            "psychological safety": (
                "Creating an environment where employees feel safe to express ideas, "
                "questions, and concerns without fear of punishment."
            ),
            "managerial responsibilities": (
                "Managers should be trained to identify distress, offer support, "
                "and not stigmatize mental health issues."
            ),
            "work-life integration": (
                "Policies supporting flexible hours, leave for mental health, "
                "and respecting boundaries after work hours."
            ),
            "stigma & language": (
                "Avoid pejorative terms. Use person-first language. "
                "Promote open conversations about mental health."
            ),
            "crisis intervention": (
                "Protocols for handling acute mental health episodes (panic attacks, "
                "suicidal ideation) at the workplace."
            ),
            "scenario-based challenges": (
                "Handling an employee's return to work after mental health leave; "
                "Managing performance issues linked to mental health."
            ),
        }

        q_lower = query.lower()
        if q_lower in all_answers:
            return all_answers[q_lower]

        return (
            f"I received your question: '{query}'. However, the AI models are not loaded "
            "in this environment, so this is a placeholder response."
        )


# -----------------------------
# Load Models (Mock or Real)
# -----------------------------
image_chatbot = None
text_chatbot = None
rag_chatbot = None

try:
    # Try to load real models if files exist and libs are available
    # We skip main import if we suspect it will fail, but let's try-catch.
    from .utils import ImageChatbot, TextChatbot

    print("Attempting to load real models...")

    image_model_path = os.path.join(settings.BASE_DIR, "image_chatbot_model.pkl")
    if os.path.exists(image_model_path):
        image_chatbot = ImageChatbot(model_path=image_model_path)

    text_model_path = os.path.join(settings.BASE_DIR, "home", "chatbot_model.pkl")
    if os.path.exists(text_model_path):
        text_chatbot = TextChatbot(
            model_path=text_model_path,
            label_encoder_path=os.path.join(settings.BASE_DIR, "home", "label_encoder.pkl"),
            semantic_data_path=os.path.join(settings.BASE_DIR, "home", "semantic_data.pkl"),
        )

    # Initialize RAG Chatbot
    rag_index_path = os.path.join(settings.BASE_DIR, "chat/data/bot.index")
    rag_answers_path = os.path.join(settings.BASE_DIR, "chat/data/answers.json")
    if os.path.exists(rag_index_path) and os.path.exists(rag_answers_path):
        rag_chatbot = RagChatbot(rag_index_path, rag_answers_path)
    else:
        print(f"RAG Chatbot files not found at {rag_index_path} or {rag_answers_path}")

except (ImportError, Exception) as e:
    print(f"Model loading failed or dependencies missing: {e}")
    print("Using MOCK chatbots.")
    # Fallback to mocks
    image_chatbot = None
    text_chatbot = None

if image_chatbot is None:
    image_chatbot = MockImageChatbot()
if text_chatbot is None:
    text_chatbot = MockTextChatbot()


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
        json_path = os.path.join(settings.BASE_DIR, "data", filename_map[topic_name])
        # Fallback to current directory if BASE_DIR/json fails
        if not os.path.exists(json_path):
            json_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f"../data/{filename_map[topic_name]}",
            )

        if not os.path.exists(json_path):
            print(f"DEBUG: JSON file not found for {topic_name} at {json_path}")
            return {}

        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON for {topic_name}: {e}")
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
    print(f"DEBUG: Searching for subtopic: '{subtopic_title}'")
    target = normalize_text(subtopic_title)

    for topic in SUPPORTED_TOPICS:
        data = load_topic_data(topic)
        if not data or "subtopics" not in data:
            continue

        for st in data["subtopics"]:
            current = normalize_text(st["title"])
            # Check for exact match or if one is contained in another (for partial matches)
            if target == current or target in current or current in target:
                print(f"DEBUG: Match found in {topic}! '{st['title']}'")
                return [q["question"] for q in st["questions"]]

    print("DEBUG: No matching subtopic found.")
    return []


def get_answer_for_question(question_text):
    print(f"DEBUG: Searching for answer to: '{question_text}'")
    target = normalize_text(question_text)

    for topic in SUPPORTED_TOPICS:
        data = load_topic_data(topic)
        if not data or "subtopics" not in data:
            continue

        for st in data["subtopics"]:
            for q in st["questions"]:
                current = normalize_text(q["question"])
                if target == current:
                    print(f"DEBUG: Answer found in {topic} for '{q['question']}'")
                    return q["answer"]

    print("DEBUG: No answer found in JSON.")
    return None


@csrf_exempt
def chatbot_response(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = json.loads(request.body)
        user_question = data.get("message", "").strip()
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
            # Fallback to TextChatbot defaults if JSON is empty or missing
            if not subtopics and text_chatbot:
                subtopics = text_chatbot.get_questions_by_type(irc_type)

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

    # 4. Check RAG Chatbot (New Faiss Integration)
    if rag_chatbot:
        rag_answer = rag_chatbot.get_answer(user_question)
        if rag_answer:
            return JsonResponse({"response": {"message": rag_answer, "type": "answer"}})

    # 5. Integrate LLM (RAG)
    # If no direct match in JSON, ask the LLM
    print(f"DEBUG: asking LLM for '{user_question}'")
    llm_engine = LLMEngine.get_instance()
    # Only query LLM if it's ready or we want to try initializing it
    llm_response = llm_engine.generate_answer(user_question)

    if (
        llm_response
        and "answering using context" not in llm_response.lower()
        and "model is not ready" not in llm_response.lower()
    ):
        return JsonResponse({"response": {"message": llm_response, "type": "answer"}})
    # If LLM fails or is not ready, fall through to old logic (or maybe we want to show the error?)
    if "Model is not ready" in llm_response:
        print(f"DEBUG: LLM not ready: {llm_response}")

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
