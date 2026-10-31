import io

from langchain_core.messages import AIMessage
from PIL import Image

USER_A = {"Authorization": "Bearer teste-usuario-a"}
USER_B = {"Authorization": "Bearer teste-usuario-b"}
UNO = {
    "make": "Fiat",
    "model": "Uno",
    "year": "2015",
    "plate": "abc1d23",
    "description": "Risco na porta",
}


def findings(**overrides) -> dict:
    """Build well-founded findings that a scenario can override."""
    base = {
        "vehicle_match": {"status": "matches", "reason": "Condiz", "evidence_ids": ["P1"]},
        "photo_assessments": [{"evidence_id": "P1", "usable": True, "reason": "nitida"}],
        "damages": [
            {
                "evidence_id": "P1",
                "location": "porta esquerda",
                "damage_type": "risco",
                "severity": "moderate",
                "category": "aesthetic",
                "confidence": "high",
                "observation": "Risco de 20 cm",
            }
        ],
        "hypotheses": [
            {
                "description": "Atrito com objeto",
                "confidence": "medium",
                "evidence_ids": ["E1", "P1"],
                "what_would_confirm": "Inspecao",
            }
        ],
        "conflicts": [],
        "evaluated_categories": ["aesthetic"],
        "limitations": ["Mecanica nao avaliada por foto"],
    }

    return {**base, **overrides}


def call(name: str, args: dict, call_id: str = "c1") -> dict:
    """Build a tool call as the model would emit it."""
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def conclude(**overrides) -> AIMessage:
    """Build the orchestrator turn that concludes the investigation."""
    args = {
        "summary": "Resumo",
        "recommendation": "Levar a oficina",
        "needs_user_input": False,
        "questions": [],
        "follow_up_questions": [],
        "requires_in_person_inspection": False,
        "inspection_reason": "",
    }

    return AIMessage(
        content="", tool_calls=[call("submit_conclusion", {**args, **overrides}, "end")]
    )


def bodywork() -> AIMessage:
    """Build the turn where the orchestrator calls the bodywork specialist."""
    return AIMessage(
        content="Vou acionar a funilaria.",
        tool_calls=[call("analyze_bodywork", {"photo_ids": ["P1"], "focus": "porta"})],
    )


def photo() -> tuple:
    """Return a small JPEG in upload format."""
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), "gray").save(buffer, "JPEG")

    return ("photos", ("foto.jpg", buffer.getvalue(), "image/jpeg"))
