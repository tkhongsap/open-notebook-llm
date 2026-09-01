from fastapi import APIRouter, HTTPException

from api.artifact_service import generate_notebook_artifact
from api.models import NotebookArtifactCreate, NotebookArtifactResponse
from open_notebook.exceptions import NotFoundError, OpenNotebookError

router = APIRouter()


@router.post(
    "/notebooks/{notebook_id}/artifacts",
    response_model=NotebookArtifactResponse,
)
async def create_notebook_artifact(
    notebook_id: str, request: NotebookArtifactCreate
) -> NotebookArtifactResponse:
    """Generate a grounded, durable Studio artifact from notebook context."""
    try:
        note, command_id, execution = await generate_notebook_artifact(
            notebook_id=notebook_id,
            artifact_kind=request.artifact_kind,
            custom_instructions=request.custom_instructions,
            model_id=request.model_id,
        )
        return NotebookArtifactResponse(
            id=note.id or "",
            title=note.title,
            content=note.content,
            note_type=note.note_type,
            created=str(note.created),
            updated=str(note.updated),
            command_id=command_id,
            artifact_kind=request.artifact_kind,
            model=execution.to_dict(),
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except OpenNotebookError:
        raise
