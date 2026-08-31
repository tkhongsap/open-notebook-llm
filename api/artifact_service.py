"""Grounded Notebook Studio artifact generation."""

from dataclasses import dataclass
from typing import Dict

from ai_prompter import Prompter
from langchain_core.messages import HumanMessage, SystemMessage

from api.models import NotebookArtifactKind
from open_notebook.ai.provision import provision_langchain_model
from open_notebook.domain.notebook import Note, Notebook
from open_notebook.exceptions import InvalidInputError, OpenNotebookError
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.text_utils import clean_thinking_content, extract_text_content


@dataclass(frozen=True)
class ArtifactSpec:
    title: str
    instructions: str


ARTIFACT_SPECS: Dict[NotebookArtifactKind, ArtifactSpec] = {
    "briefing_doc": ArtifactSpec(
        title="Briefing document",
        instructions=(
            "Write a concise executive briefing with an overview, key findings, "
            "important evidence, tensions or uncertainties, and recommended next questions."
        ),
    ),
    "study_guide": ArtifactSpec(
        title="Study guide",
        instructions=(
            "Create a structured study guide with learning objectives, a topic outline, "
            "key terms, worked explanations, and review questions."
        ),
    ),
    "faq": ArtifactSpec(
        title="Frequently asked questions",
        instructions=(
            "Create a practical FAQ with the most important questions a new reader would "
            "ask and concise, evidence-grounded answers."
        ),
    ),
    "timeline": ArtifactSpec(
        title="Timeline",
        instructions=(
            "Build a chronological timeline from dates and sequences in the sources. "
            "If exact dates are unavailable, explicitly label the result as a thematic sequence."
        ),
    ),
    "mind_map": ArtifactSpec(
        title="Mind map",
        instructions=(
            "Build a navigable text mind map using nested Markdown bullets: central topic, "
            "major branches, sub-branches, and the relationships between them."
        ),
    ),
    "flashcards": ArtifactSpec(
        title="Flashcards",
        instructions=(
            "Create 15 high-value flashcards as a Markdown table with Front, Back, and "
            "Evidence columns. Favor understanding over trivia."
        ),
    ),
    "quiz": ArtifactSpec(
        title="Quiz",
        instructions=(
            "Create a 10-question quiz mixing multiple choice and short answer. Put the "
            "answer key after a divider and explain every answer with evidence."
        ),
    ),
}


async def generate_notebook_artifact(
    notebook_id: str,
    artifact_kind: NotebookArtifactKind,
    custom_instructions: str | None = None,
    model_id: str | None = None,
) -> tuple[Note, str | None]:
    """Generate and save one grounded Studio artifact for a notebook."""
    notebook = await Notebook.get(notebook_id)
    context = (await notebook.get_context()).strip()
    if not context:
        raise InvalidInputError(
            "Add at least one processed source or substantive note before generating an artifact"
        )

    spec = ARTIFACT_SPECS[artifact_kind]
    system_prompt = Prompter(prompt_template="artifact/generate").render(
        data={
            "artifact_title": spec.title,
            "artifact_instructions": spec.instructions,
            "custom_instructions": (custom_instructions or "").strip(),
        }
    )
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=context)]

    try:
        chain = await provision_langchain_model(
            str(messages),
            model_id,
            "transformation",
            max_tokens=8192,
        )
        response = await chain.ainvoke(messages)
        content = clean_thinking_content(extract_text_content(response.content)).strip()
        if not content:
            raise InvalidInputError("The selected model returned an empty artifact")

        note = Note(title=spec.title, content=content, note_type="ai")
        command_id = await note.save()
        await note.add_to_notebook(notebook_id)
        return note, str(command_id) if command_id else None
    except OpenNotebookError:
        raise
    except Exception as exc:
        error_class, user_message = classify_error(exc)
        raise error_class(user_message) from exc
