"""
Cloud.ru (Qwen) Patched LLM Client

Provides a patched version of OpenAIGenericClient specifically for Cloud.ru/Qwen models.

Problem:
    Qwen models copy the entire JSON schema structure into their responses instead
    of returning only the data conforming to that schema. This causes ValidationError
    in Pydantic when graphiti_core tries to parse the response.

    Example of problematic Qwen response:
    {
        "properties": {...},
        "required": [...],
        "title": "EdgeDuplicate",
        "type": "object",
        "duplicate_facts": [],      # Actual data mixed with schema
        "contradicted_facts": [0],
        "fact_type": "DEFAULT"
    }

Solution:
    Instead of appending the JSON *schema* (`model_json_schema()`) to the prompt —
    which literally puts the word `properties` in front of the model for it to echo —
    this patched client appends a flat *example* of the expected answer, built from the
    Pydantic model without an LLM (see `response_examples.example_for_model`). The
    example has no schema scaffolding to copy, so the `properties`-wrapper class of
    failure has nothing to latch onto.

    A manager-side guard (`PipGraphManager._guard_summaries`) is the second line of
    defence: it never lets a previously-good summary be overwritten with an empty one.

Reference:
    See pipgraph-obsidian/.docs/plans/fix-json-schema/ for the full diagnosis and design.
"""

import json
import logging
import typing
from pydantic import BaseModel

from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.llm_client.client import MULTILINGUAL_EXTRACTION_RESPONSES
from graphiti_core.llm_client.config import ModelSize
from graphiti_core.prompts.extract_nodes import EntitySummary
from graphiti_core.prompts.models import Message

from app.services.graphiti.response_examples import example_for_model

logger = logging.getLogger(__name__)


class CloudRuPatchedClient(OpenAIGenericClient):
    """
    Patched OpenAI client for Cloud.ru (Qwen) models.

    Overrides generate_response() to provide clearer JSON schema instructions
    that help Qwen models understand they should return data only, not the schema.

    All other functionality remains identical to OpenAIGenericClient.
    """

    async def generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, typing.Any]:
        """
        Generate response with Qwen-friendly JSON schema instructions.

        This method is identical to OpenAIGenericClient.generate_response()
        except for the prompt instruction format (line that appends schema to messages).

        Args:
            messages: List of conversation messages
            response_model: Pydantic model defining expected response structure
            max_tokens: Maximum tokens in response
            model_size: Size of model to use

        Returns:
            dict: Parsed JSON response from LLM
        """
        if max_tokens is None:
            max_tokens = self.max_tokens

        retry_count = 0
        last_error = None

        # PATCHED: show the model a flat EXAMPLE of the answer, not the JSON schema.
        # Feeding `model_json_schema()` put the literal word `properties` in front of
        # Qwen, which it then echoes as a wrapper around the real data
        # ({"properties": {"summary": ...}}) — silently wiping summaries downstream.
        # An example response has no schema scaffolding to copy and is self-documenting
        # (placeholders carry each field's description). Built without an LLM.
        if response_model is not None:
            example = json.dumps(
                example_for_model(response_model), ensure_ascii=False, indent=2
            )
            messages[-1].content += (
                '\n\nReturn ONLY a JSON object with exactly these keys, in exactly '
                'this shape. Replace each placeholder (text in angle brackets) with '
                f'real data.\n\n{example}'
            )

        # Add multilingual extraction instructions
        messages[0].content += MULTILINGUAL_EXTRACTION_RESPONSES

        # Retry logic (unchanged from parent class)
        while retry_count <= self.MAX_RETRIES:
            try:
                response = await self._generate_response(
                    messages, response_model, max_tokens=max_tokens, model_size=model_size
                )

                # DEBUG (empty-summary hunt): extract_summary feeds straight into
                # `node.summary = summary_response.get('summary', '')` in graphiti's
                # extract_attributes_from_node — a blank/missing 'summary' here silently
                # wipes a previously-good summary on the next bulk save. Log the raw
                # response so we can tell apart: empty string vs missing key vs schema
                # leakage (the Qwen quirk this client patches around).
                if response_model is EntitySummary:
                    summary_val = (
                        response.get('summary') if isinstance(response, dict) else None
                    )
                    if not summary_val:
                        logger.warning(
                            "[extract_summary] LLM returned EMPTY/missing summary "
                            f"(model_size={model_size}, retry={retry_count}, "
                            f"keys={list(response.keys()) if isinstance(response, dict) else type(response).__name__}, "
                            f"raw={response!r})"
                        )
                    else:
                        logger.debug(
                            f"[extract_summary] ok, len={len(summary_val)} "
                            f"(model_size={model_size}, retry={retry_count})"
                        )

                return response
            except Exception as e:
                last_error = e

                # Don't retry if we've hit the max retries
                if retry_count >= self.MAX_RETRIES:
                    raise

                retry_count += 1

                # Construct error context for retry
                error_context = (
                    f'The previous response attempt was invalid. '
                    f'Error type: {e.__class__.__name__}. '
                    f'Error details: {str(e)}. '
                    f'Please try again with a valid response, ensuring the output matches '
                    f'the expected format and constraints.'
                )

                error_message = Message(role='user', content=error_context)
                messages.append(error_message)

        # If we somehow get here, raise the last error
        raise last_error or Exception('Max retries exceeded with no specific error')
