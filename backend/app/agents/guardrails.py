"""
Guardrails execution module to protect against prompt injection and malicious inputs.

Because Lumen bypasses `agent.run()`, we manually execute the Agno guardrails
here before passing the user input to the RAG stream.
"""

from __future__ import annotations

from collections.abc import Sequence
import logging

from agno.exceptions import InputCheckError
from agno.guardrails import BaseGuardrail, PromptInjectionGuardrail
from agno.run.agent import RunInput

logger = logging.getLogger("agents.guardrails")

# We can easily add PIIDetectionGuardrail or others to this list later.
ACTIVE_GUARDRAILS: Sequence[BaseGuardrail] = [PromptInjectionGuardrail()]


def execute_guardrails(user_message: str) -> None:
    """
    Check the user message against all configured Agno guardrails natively.
    Raises:
        InputCheckError: If any guardrail trigger condition is met.
    """
    if not user_message:
        return

    run_input = RunInput(input_content=user_message)

    for guardrail in ACTIVE_GUARDRAILS:
        try:
            guardrail.check(run_input)
        except InputCheckError as e:
            logger.warning("Guardrail %s triggered: %s", guardrail.__class__.__name__, e.message)
            raise
