from typing import Any
from api.data.marhaba_context import MARHABA_CONTEXT

def _handle_general(state: dict) -> dict:
    model = state["model"]
    question = state["question"]
    name = state["name"]
    history = state.get("history", [])
    is_first_message = state.get("is_first_message", False)

    history_lines = []
    for item in history:
        role = item.get("role")
        text = item.get("text")
        if role and text:
            history_lines.append(f"{role.title()}: {text}")
    history_block = "\n".join(history_lines)

    conversation_prefix = (
        f"Conversation so far:\n{history_block}\n" if history_block else ""
    )
    greeting_instruction = (
        "Greet the user by name at the start." if is_first_message else "Do not greet again."
    )

    prompt = (
        f"{MARHABA_CONTEXT}\n\n"
        f"User Name: {name}\n"
        f"{conversation_prefix}"
        f"User Question: {question}\n\n"
        "Please provide a helpful and accurate response based on Marhaba Haji's services. "
        "Keep the answer short (2-4 sentences) and warm. "
        f"{greeting_instruction}"
    )

    response = model.generate_content(prompt)
    state["answer"] = response.text
    return state
