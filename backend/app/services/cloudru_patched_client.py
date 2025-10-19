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
    This patched client modifies the prompt instruction to be more explicit:
    - Instead of: "Respond with a JSON object in the following format:"
    - Uses: "Provide your response as valid JSON matching this schema (return data only, not the schema):"

    This single-line change helps Qwen understand it should return only data.

Reference:
    See backend/docs/attend/explore_prompts_validation.md for detailed analysis.
"""

import json
import typing
from pydantic import BaseModel

from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.llm_client.client import MULTILINGUAL_EXTRACTION_RESPONSES
from graphiti_core.llm_client.config import ModelSize
from graphiti_core.prompts.models import Message


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

        # PATCHED LINE: More explicit instruction for Qwen
        if response_model is not None:
            serialized_model = json.dumps(response_model.model_json_schema())
            messages[-1].content += (
                f'\n\nProvide your response as valid JSON matching this schema '
                f'(return data only, not the schema):\n\n{serialized_model}'
            )

        # Add multilingual extraction instructions
        messages[0].content += MULTILINGUAL_EXTRACTION_RESPONSES

        # Retry logic (unchanged from parent class)
        while retry_count <= self.MAX_RETRIES:
            try:
                response = await self._generate_response(
                    messages, response_model, max_tokens=max_tokens, model_size=model_size
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
