"""M2: Mission → ThesisDecomposition (single LLM call, structured output)."""
from __future__ import annotations

from typing import Any

from ..prompts import load_prompt
from ..schemas import Mission, ThesisDecomposition
from ..state import GraphState


def thesis_decomposer(
    state: GraphState,
    *,
    llm: Any | None = None,
) -> dict:
    mission: Mission = state["mission"]
    if llm is None:
        from ..llm import DEEP_THINK_MODEL, get_llm
        llm = get_llm(DEEP_THINK_MODEL)

    structured = llm.with_structured_output(ThesisDecomposition)
    response: ThesisDecomposition = structured.invoke([
        ("system", load_prompt("thesis_decomposer")),
        ("user", mission.model_dump_json(indent=2)),
    ])

    # Force spine alignment regardless of what the model emitted.
    fixed_subs = [s.model_copy(update={"mission_id": mission.id}) for s in response.sub_themes]
    final = response.model_copy(update={"mission_id": mission.id, "sub_themes": fixed_subs})
    return {"decomposition": final}
