from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.podcast_service import PodcastService
from api.routers.podcasts import _retry_briefing_suffix, retry_podcast_episode
from open_notebook.database.async_migrate import AsyncMigrationManager
from open_notebook.podcasts.models import EpisodeProfile, PodcastEpisode, SpeakerProfile


def episode_profile() -> EpisodeProfile:
    return EpisodeProfile(
        id="episode_profile:overview",
        name="overview",
        description="Audio overview",
        speaker_config="speaker_profile:hosts",
        outline_llm="model:language",
        transcript_llm="model:language",
        default_briefing="Explain the selected evidence.",
        num_segments=4,
    )


def speaker_profile() -> SpeakerProfile:
    return SpeakerProfile(
        id="speaker_profile:hosts",
        name="hosts",
        description="Two hosts",
        voice_model="model:voice",
        speakers=[
            {
                "name": "Host",
                "voice_id": "alloy",
                "backstory": "Research host",
                "personality": "Curious and concise",
            }
        ],
    )


@pytest.mark.asyncio
async def test_submission_persists_visible_episode_before_queueing() -> None:
    saved_states: list[tuple[str | None, list[str]]] = []

    async def fake_save(episode: PodcastEpisode) -> PodcastEpisode:
        episode.id = episode.id or "episode:queued"
        saved_states.append(
            (
                str(episode.command) if episode.command else None,
                [str(value) for value in episode.notebook_ids],
            )
        )
        return episode

    with (
        patch.object(
            EpisodeProfile,
            "get_by_name",
            new=AsyncMock(return_value=episode_profile()),
        ),
        patch.object(
            SpeakerProfile,
            "resolve",
            new=AsyncMock(return_value=speaker_profile()),
        ),
        patch("api.podcast_service.Notebook.get", new=AsyncMock(return_value=object())) as get_notebook,
        patch.object(PodcastEpisode, "save", new=fake_save),
        patch("api.podcast_service.submit_command", return_value="command:audio") as submit,
    ):
        job_id = await PodcastService.submit_generation_job(
            episode_profile_name="overview",
            speaker_profile_name="speaker_profile:hosts",
            episode_name="Notebook Audio Overview",
            notebook_id="notebook:one",
            notebook_ids=["notebook:one", "notebook:two"],
            content="Grounded notebook evidence",
        )

    assert job_id == "command:audio"
    assert saved_states == [
        (None, ["notebook:one", "notebook:two"]),
        ("command:audio", ["notebook:one", "notebook:two"]),
    ]
    assert get_notebook.await_count == 2
    command_input = submit.call_args.args[2]
    assert command_input["episode_id"] == "episode:queued"
    assert command_input["notebook_ids"] == ["notebook:one", "notebook:two"]


@pytest.mark.asyncio
async def test_failed_queue_submission_removes_placeholder() -> None:
    deleted: list[str] = []

    async def fake_save(episode: PodcastEpisode) -> PodcastEpisode:
        episode.id = "episode:placeholder"
        return episode

    async def fake_delete(episode: PodcastEpisode) -> None:
        deleted.append(str(episode.id))

    with (
        patch.object(
            EpisodeProfile,
            "get_by_name",
            new=AsyncMock(return_value=episode_profile()),
        ),
        patch.object(
            SpeakerProfile,
            "resolve",
            new=AsyncMock(return_value=speaker_profile()),
        ),
        patch.object(PodcastEpisode, "save", new=fake_save),
        patch.object(PodcastEpisode, "delete", new=fake_delete),
        patch("api.podcast_service.submit_command", side_effect=RuntimeError("queue down")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await PodcastService.submit_generation_job(
                episode_profile_name="overview",
                speaker_profile_name="speaker_profile:hosts",
                episode_name="Audio Overview",
                content="Evidence",
            )

    assert exc_info.value.status_code == 500
    assert deleted == ["episode:placeholder"]


@pytest.mark.asyncio
async def test_incomplete_profile_is_rejected_before_creating_queue_item() -> None:
    incomplete = episode_profile()
    incomplete.outline_llm = None
    voice_missing = speaker_profile()
    voice_missing.voice_model = None

    with (
        patch.object(
            EpisodeProfile,
            "get_by_name",
            new=AsyncMock(return_value=incomplete),
        ),
        patch.object(
            SpeakerProfile,
            "resolve",
            new=AsyncMock(return_value=voice_missing),
        ),
        patch.object(PodcastEpisode, "save", new=AsyncMock()) as save,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await PodcastService.submit_generation_job(
                episode_profile_name="overview",
                speaker_profile_name="hosts",
                episode_name="Audio Overview",
                content="Evidence",
            )

    assert exc_info.value.status_code == 409
    assert "outline language model" in exc_info.value.detail
    assert "text-to-speech voice model" in exc_info.value.detail
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_episodes_filters_in_database_by_notebook() -> None:
    row = {
        "id": "episode:one",
        "name": "Overview",
        "episode_profile": {"name": "overview"},
        "speaker_profile": {"name": "hosts"},
        "briefing": "Explain",
        "content": "Evidence",
        "notebook_ids": ["notebook:one"],
        "audio_file": None,
        "command": "command:one",
    }

    with (
        patch("api.podcast_service.Notebook.get", new=AsyncMock(return_value=object())) as get_notebook,
        patch("api.podcast_service.repo_query", new=AsyncMock(return_value=[row])) as query,
    ):
        episodes = await PodcastService.list_episodes("notebook:one")

    assert [str(value) for value in episodes[0].notebook_ids] == ["notebook:one"]
    get_notebook.assert_awaited_once_with("notebook:one")
    query.assert_awaited_once()
    query_call = query.await_args
    assert query_call is not None
    assert "$notebook_id IN notebook_ids" in query_call.args[0]
    assert str(query_call.args[1]["notebook_id"]) == "notebook:one"


def test_migration_25_defines_notebook_links_and_is_registered() -> None:
    root = Path(__file__).parent.parent
    sql = (root / "open_notebook/database/migrations/25.surrealql").read_text()
    down = (root / "open_notebook/database/migrations/25_down.surrealql").read_text()

    assert "array<record<notebook>>" in sql
    assert "idx_episode_notebooks" in sql
    assert "REMOVE FIELD IF EXISTS notebook_ids" in down
    assert len(AsyncMigrationManager().up_migrations) == 25
    assert len(AsyncMigrationManager().down_migrations) == 25


@pytest.mark.asyncio
async def test_retry_keeps_failed_episode_when_replacement_cannot_queue() -> None:
    failed_episode = AsyncMock()
    failed_episode.id = "episode:failed"
    failed_episode.name = "Failed overview"
    failed_episode.content = "Evidence"
    failed_episode.episode_profile = {"name": "overview"}
    failed_episode.speaker_profile = {"name": "hosts"}
    failed_episode.notebook_ids = ["notebook:one"]
    failed_episode.audio_file = None
    failed_episode.get_job_detail.return_value = {
        "status": "failed",
        "error_message": "voice unavailable",
    }

    with (
        patch.object(
            PodcastService,
            "get_episode",
            new=AsyncMock(return_value=failed_episode),
        ),
        patch.object(
            PodcastService,
            "submit_generation_job",
            new=AsyncMock(
                side_effect=HTTPException(status_code=409, detail="setup incomplete")
            ),
        ),
        patch("api.routers.podcasts._delete_episode_audio") as delete_audio,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await retry_podcast_episode("episode:failed")

    assert exc_info.value.status_code == 409
    failed_episode.delete.assert_not_awaited()
    delete_audio.assert_not_called()


def test_retry_recovers_additional_briefing_instructions() -> None:
    episode = PodcastEpisode(
        name="Overview",
        episode_profile={
            "name": "overview",
            "default_briefing": "Explain the selected evidence.",
        },
        speaker_profile={"name": "hosts"},
        briefing=(
            "Explain the selected evidence.\n\nAdditional instructions: "
            "Focus on readiness gaps and do not add unsupported facts."
        ),
        content="Evidence",
    )

    assert _retry_briefing_suffix(episode) == (
        "Focus on readiness gaps and do not add unsupported facts."
    )


def test_retry_does_not_duplicate_legacy_briefing() -> None:
    episode = PodcastEpisode(
        name="Overview",
        episode_profile={
            "name": "overview",
            "default_briefing": "Explain the selected evidence.",
        },
        speaker_profile={"name": "hosts"},
        briefing="A legacy custom briefing with no generated suffix marker.",
        content="Evidence",
    )

    assert _retry_briefing_suffix(episode) is None
