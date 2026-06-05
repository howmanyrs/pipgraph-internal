"""Build a flat, self-documenting JSON *example* from a Pydantic model — no LLM.

Why this exists:
    Qwen (and other weak MoE models) intermittently echo the *schema* we hand them
    back as the *answer* — wrapping the real data in the schema's ``properties`` key
    (``{"properties": {"summary": "..."}}`` instead of ``{"summary": "..."}``). The
    root cause is that we were appending ``model_json_schema()`` to the prompt: the
    word ``properties`` is literally in front of the model, so it copies it.

    Showing an *instance* (an example response) instead of a *schema* removes the
    wrapper key from the prompt entirely — there is nothing named ``properties`` to
    echo. Values are replaced by ``<placeholder>`` hints drawn from each field's
    description, so the example is also self-documenting.

This is pure type introspection: it tracks any change to the graphiti response
models automatically and never calls the LLM. Used from ``CloudRuPatchedClient``
(the single choke-point where ``response_model`` is visible for every call).
"""

from enum import Enum
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel


def example_for_model(model: type[BaseModel]) -> dict[str, Any]:
    """Return a dict matching ``model``'s shape, with placeholder values."""
    return {
        name: _example(field.annotation, field.description)
        for name, field in model.model_fields.items()
    }


def _example(annotation: Any, description: str | None) -> Any:
    origin = get_origin(annotation)

    # Literal[...] — show the first allowed value (check before isinstance(type)).
    if origin is Literal:
        args = get_args(annotation)
        return args[0] if args else "<...>"

    # Optional[X] / Union[...] — take the first non-None member.
    if origin is Union:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        return _example(non_none[0], description) if non_none else None

    # Collections — one example element shows the shape.
    if origin in (list, set, tuple):
        inner = get_args(annotation)
        return [_example(inner[0], description) if inner else "<...>"]

    if origin is dict:
        return {}

    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel):
            return example_for_model(annotation)
        if issubclass(annotation, Enum):
            return next(iter(annotation)).value
        if annotation in (int, float):
            return 0
        if annotation is bool:
            return False

    # str and anything unrecognised — a placeholder carrying the field's hint.
    return f"<{description}>" if description else "<...>"
