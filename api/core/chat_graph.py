from typing import Optional, TypedDict, Any
from langgraph.graph import StateGraph, END

## HANDLERS
from typing import Any, Optional
from api.handlers.flight_handler import  _handle_flight
from api.handlers.general_handler import _handle_general
from api.handlers.intent_handler import _detect_intent
from api.handlers.visa_handler import _handle_visa
from api.handlers.hotel_handler import _handle_hotel


class ChatState(TypedDict, total=False):
    question: str
    name: str
    history: list
    is_first_message: bool
    visa_context: Optional[dict]
    resolved_country: Optional[str]
    intent: str
    answer: str
    visa_context_updated: bool
    flight_context: Optional[dict]
    flight_question_index: int
    flight_data: dict
    flight_context_updated: bool
    hotel_context: Optional[dict]
    hotel_question_index: int

def build_chat_graph() -> Any:
    graph = StateGraph(ChatState)

    graph.add_node("detect_intent", _detect_intent)
    graph.add_node("handle_general", _handle_general)
    graph.add_node("handle_visa", _handle_visa)
    graph.add_node("handle_flight", _handle_flight)
    graph.add_node("handle_hotel", _handle_hotel)


    graph.set_entry_point("detect_intent")

    graph.add_conditional_edges(
        "detect_intent",
        lambda state: state.get("intent", "general"),
        {
            "visa": "handle_visa",
            "flight": "handle_flight",
            "hotel": "handle_hotel",
            "general": "handle_general",
        },
    )

    graph.add_edge("handle_general", END)
    graph.add_edge("handle_visa", END)
    graph.add_edge("handle_flight", END)
    graph.add_edge("handle_hotel", END)

    return graph.compile()


CHAT_GRAPH = build_chat_graph()