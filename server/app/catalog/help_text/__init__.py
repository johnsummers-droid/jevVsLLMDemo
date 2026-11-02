"""Help panel content for every catalog node (plan1.txt S4-S7).

Rules for writing it (S6): explain how a node works, never the scenario answers. Don't quote
the mock LLM's marker phrases or official pack text (a test scans for both), and don't give
mock error rates or say which policy rule catches which risk. Numbers that the definition
already holds (param defaults, latency, cost per call) are shown by the panel; don't repeat
them here, or they drift.

Each example runs in tests/test_help.py through the node's runner at run seed 0; its outputs
must match what is written here.
"""

from app.catalog.help_text.customer_message import CUSTOMER_MESSAGE_HELP
from app.catalog.help_text.jev_intent_router import JEV_INTENT_ROUTER_HELP
from app.catalog.help_text.jev_safety_check import JEV_SAFETY_CHECK_HELP
from app.catalog.help_text.llm_answer_generator import LLM_ANSWER_GENERATOR_HELP
from app.catalog.help_text.policy_engine import POLICY_ENGINE_HELP
from app.catalog.help_text.knowledge_lookup import KNOWLEDGE_LOOKUP_HELP
from app.catalog.help_text.human_review_queue import HUMAN_REVIEW_QUEUE_HELP
from app.catalog.help_text.customer_response import CUSTOMER_RESPONSE_HELP

__all__ = [
    "CUSTOMER_MESSAGE_HELP",
    "JEV_INTENT_ROUTER_HELP",
    "JEV_SAFETY_CHECK_HELP",
    "LLM_ANSWER_GENERATOR_HELP",
    "POLICY_ENGINE_HELP",
    "KNOWLEDGE_LOOKUP_HELP",
    "HUMAN_REVIEW_QUEUE_HELP",
    "CUSTOMER_RESPONSE_HELP",
]
