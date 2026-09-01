import os

from ai_prompter import Prompter
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from loguru import logger
from typing_extensions import TypedDict

from open_notebook.ai.provision import provision_langchain_model
from open_notebook.domain.notebook import Source
from open_notebook.domain.transformation import DefaultPrompts, Transformation
from open_notebook.exceptions import OpenNotebookError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.text_utils import extract_text_content

DEFAULT_TRANSFORMATION_MAX_TOKENS = 2048
MIN_TRANSFORMATION_MAX_TOKENS = 128
MAX_TRANSFORMATION_MAX_TOKENS = 32768


def get_transformation_max_tokens() -> int:
    """Return a safe output-token ceiling for source transformations.

    Transformations run inside the source-processing command. Leaving a very
    large ceiling here lets verbose or reasoning-heavy local models monopolize
    a single-worker deployment for many minutes, which makes ingestion appear
    stuck and prevents chat or Studio from using the new source.
    """
    raw_value = os.getenv("OPEN_NOTEBOOK_TRANSFORMATION_MAX_TOKENS", "").strip()
    if not raw_value:
        return DEFAULT_TRANSFORMATION_MAX_TOKENS

    try:
        value = int(raw_value)
    except ValueError:
        logger.warning(
            "Ignoring invalid OPEN_NOTEBOOK_TRANSFORMATION_MAX_TOKENS={!r}; "
            "using {}",
            raw_value,
            DEFAULT_TRANSFORMATION_MAX_TOKENS,
        )
        return DEFAULT_TRANSFORMATION_MAX_TOKENS

    if not MIN_TRANSFORMATION_MAX_TOKENS <= value <= MAX_TRANSFORMATION_MAX_TOKENS:
        logger.warning(
            "Ignoring out-of-range OPEN_NOTEBOOK_TRANSFORMATION_MAX_TOKENS={}; "
            "expected {}..{}, using {}",
            value,
            MIN_TRANSFORMATION_MAX_TOKENS,
            MAX_TRANSFORMATION_MAX_TOKENS,
            DEFAULT_TRANSFORMATION_MAX_TOKENS,
        )
        return DEFAULT_TRANSFORMATION_MAX_TOKENS

    return value


class TransformationState(TypedDict):
    input_text: str
    source: Source
    transformation: Transformation
    output: str


async def run_transformation(state: dict, config: RunnableConfig) -> dict:
    source_obj = state.get("source")
    source: Source = source_obj if isinstance(source_obj, Source) else None  # type: ignore[assignment]
    content = state.get("input_text")
    assert source or content, "No content to transform"
    transformation: Transformation = state["transformation"]

    try:
        if not content:
            content = source.full_text
        # transformation.prompt is user-controlled free text. Never compile it as
        # Jinja template *source* (Prompter(template_text=...)) - pass it as a
        # plain render variable into a fixed, developer-authored template instead.
        # See docs/7-DEVELOPMENT/security.md (GHSA-f35w-wx37-26q7).
        instructions = transformation.prompt
        default_prompts: DefaultPrompts = DefaultPrompts(transformation_instructions=None)
        if default_prompts.transformation_instructions:
            instructions = f"{default_prompts.transformation_instructions}\n\n{instructions}"

        system_prompt = Prompter(prompt_template="transformation/execute").render(
            data={**state, "instructions": instructions}
        )
        content_str = str(content) if content else ""
        payload = [SystemMessage(content=system_prompt), HumanMessage(content=content_str)]
        chain = await provision_langchain_model(
            str(payload),
            config.get("configurable", {}).get("model_id"),
            "transformation",
            max_tokens=get_transformation_max_tokens(),
            openai_compatible_extra_body={
                "chat_template_kwargs": {"enable_thinking": False}
            },
        )

        response = await chain.ainvoke(payload)

        # Clean thinking content from the response
        response_content = extract_text_content(response.content)
        cleaned_content = clean_thinking_content(response_content)

        if source:
            await source.add_insight(transformation.title, cleaned_content)

        return {
            "output": cleaned_content,
        }
    except OpenNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        raise error_class(user_message) from e


agent_state = StateGraph(TransformationState)
agent_state.add_node("agent", run_transformation)  # type: ignore[type-var]
agent_state.add_edge(START, "agent")
agent_state.add_edge("agent", END)
graph = agent_state.compile()
