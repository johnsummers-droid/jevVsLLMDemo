from app.catalog.definitions import human, io, jev, llm, tool
from app.models import NodeDefinition

# Palette order: source first, sink last.
ALL_DEFINITIONS: list[NodeDefinition] = [
    io.CUSTOMER_MESSAGE,
    *jev.DEFINITIONS,
    *llm.DEFINITIONS,
    *tool.DEFINITIONS,
    *human.DEFINITIONS,
    io.CUSTOMER_RESPONSE,
]
