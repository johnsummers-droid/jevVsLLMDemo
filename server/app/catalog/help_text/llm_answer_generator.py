"""Help panel content for the llm_answer_generator node. The rules are in __init__.py."""

from app.catalog.help_text.common import REPEAT_NOTE
from app.models import HelpExample, NodeHelp

LLM_ANSWER_GENERATOR_HELP = NodeHelp(
    summary="An LLM node that writes the reply to the customer from their message, "
            "optionally using help-center articles as context.",
    placement="After the router (or on one of its branches), before the customer response. "
              "Feed it a knowledge lookup's Docs on the Context input to ground its answers.",
    how_it_works=[
        "The model reads the system prompt, the message and any context docs, and writes a "
        "free-text answer.",
        "Unlike a Jev node it doesn't make a bounded decision: its output is open-ended text, "
        "so it can be wrong, invent details or be talked into saying things it shouldn't.",
        "Cost depends on the tokens it reads and writes and on the model tier; time grows "
        "with every token it writes.",
        "Questions that need specific product facts go better when the answer is grounded in "
        "matching docs.",
        "The model's own safety filter can refuse a message. No reply goes out, the request "
        "counts as blocked, and the node shows \"N blocked\".",
        REPEAT_NOTE,
    ],
    inputs={
        "text": "The customer's message.",
        "context": "Optional help-center docs from a knowledge lookup.",
    },
    params={
        "model": "Small is faster and cheaper; large is slower, costs more per token and is "
                 "generally more reliable.",
        "max_tokens": "The longest answer it may write. Longer answers take more time and "
                      "cost more.",
        "prompt": "The system prompt: instructions on how to behave. What you write here "
                  "affects how it handles tricky messages.",
    },
    outputs={"text": "The answer it wrote."},
    example=HelpExample(
        ticket_id="p-01",
        input_text=("I was charged twice for my March invoice. Can you check what "
                    "happened?"),
        outputs={
            "text": "Thanks for reaching out about your bill. I have checked your account and "
                    "will walk you through the charges and the next steps.",
        },
        explanation="With the default settings the model writes a reply to a double-charge "
                    "question. The node badge shows its tokens, time and cost during a run.",
    ),
    tips=[
        "Check the answer before it reaches the customer: a policy engine after this node "
        "catches answers that break your rules.",
        "The small tier is much cheaper; try it on simple branches and keep an eye on the "
        "unsafe-release rate.",
    ],
)
