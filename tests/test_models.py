"""Tests for iphoto.models — pure-logic functions that don't need Photos.app."""

from datetime import datetime, timezone
from pathlib import Path

from iphoto.models import (
    MomentGroup,
    SessionState,
    VideoInfo,
    filter_ambiguous_filenames,
    format_bytes,
    video_from_dict,
    video_to_dict,
)


def _make_video(**overrides) -> VideoInfo:
    defaults = dict(
        uuid="test-uuid-1",
        filename="ABC123.mov",
        original_filename="IMG_0001.MOV",
        date_created=datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc),
        date_modified=datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc),
        size_bytes=1_073_741_824,
        duration_seconds=120.5,
        width=1920,
        height=1080,
    )
    defaults.update(overrides)
    return VideoInfo(**defaults)


# --- format_bytes ---


class TestFormatBytes:
    def test_gigabytes(self):
        assert format_bytes(2_147_483_648) == "2.00 GB"

    def test_megabytes(self):
        assert format_bytes(524_288_000) == "500.0 MB"

    def test_small_megabytes(self):
        assert format_bytes(1_048_576) == "1.0 MB"

    def test_zero(self):
        assert format_bytes(0) == "0.0 MB"

    def test_just_under_one_gb(self):
        result = format_bytes(1_073_741_823)
        assert "MB" in result


# --- video_to_dict / video_from_dict ---


class TestVideoSerialization:
    def test_roundtrip(self):
        video = _make_video(location=(51.5074, -0.1278), place_name="London")
        d = video_to_dict(video)
        restored = video_from_dict(d)

        assert restored.uuid == video.uuid
        assert restored.original_filename == video.original_filename
        assert restored.size_bytes == video.size_bytes
        assert restored.location == video.location
        assert restored.place_name == video.place_name
        assert restored.date_created == video.date_created

    def test_dates_are_isoformat_strings(self):
        d = video_to_dict(_make_video())
        assert isinstance(d["date_created"], str)
        assert isinstance(d["date_modified"], str)
        # Should parse back
        datetime.fromisoformat(d["date_created"])

    def test_extra_keys_ignored(self):
        d = video_to_dict(_make_video())
        d["unknown_field"] = "should be ignored"
        restored = video_from_dict(d)
        assert restored.uuid == "test-uuid-1"

    def test_none_location_roundtrip(self):
        video = _make_video(location=None)
        d = video_to_dict(video)
        restored = video_from_dict(d)
        assert restored.location is None


# --- filter_ambiguous_filenames ---


class TestFilterAmbiguousFilenames:
    def test_no_duplicates(self):
        videos = [
            _make_video(uuid="a", original_filename="IMG_0001.MOV"),
            _make_video(uuid="b", original_filename="IMG_0002.MOV"),
        ]
        safe, failures = filter_ambiguous_filenames(videos)
        assert len(safe) == 2
        assert len(failures) == 0

    def test_duplicates_filtered(self):
        videos = [
            _make_video(uuid="a", original_filename="IMG_0001.MOV"),
            _make_video(uuid="b", original_filename="IMG_0001.MOV"),
            _make_video(uuid="c", original_filename="IMG_0002.MOV"),
        ]
        safe, failures = filter_ambiguous_filenames(videos)
        assert len(safe) == 1
        assert safe[0].uuid == "c"
        assert "a" in failures
        assert "b" in failures

    def test_allow_ambiguous_bypasses_filter(self):
        videos = [
            _make_video(uuid="a", original_filename="IMG_0001.MOV"),
            _make_video(uuid="b", original_filename="IMG_0001.MOV"),
        ]
        safe, failures = filter_ambiguous_filenames(videos, allow_ambiguous=True)
        assert len(safe) == 2
        assert len(failures) == 0

    def test_empty_input(self):
        safe, failures = filter_ambiguous_filenames([])
        assert safe == []
        assert failures == {}


# --- SessionState.to_dict / from_dict ---


class TestSessionStateSerialization:
    def test_roundtrip(self):
        session = SessionState(
            staging_path=Path("/tmp/staging"),
            external_path=Path("/Volumes/Archive"),
            all_selected_uuids=["uuid-1", "uuid-2"],
            remaining_uuids=["uuid-2"],
            threshold_mb=500.0,
            delete_enabled=True,
            total_exported=1,
            total_archived=1,
            total_deleted=0,
        )
        d = session.to_dict()
        restored = SessionState.from_dict(d)

        assert restored.session_id == session.session_id
        assert restored.staging_path == session.staging_path
        assert restored.external_path == session.external_path
        assert restored.all_selected_uuids == session.all_selected_uuids
        assert restored.remaining_uuids == session.remaining_uuids
        assert restored.threshold_mb == session.threshold_mb
        assert restored.delete_enabled == session.delete_enabled
        assert restored.total_exported == 1

    def test_roundtrip_with_videos(self):
        video = _make_video()
        session = SessionState(
            staging_path=Path("/tmp/staging"),
            external_path=Path("/Volumes/Archive"),
            videos=[video],
        )
        d = session.to_dict()
        restored = SessionState.from_dict(d)
        assert len(restored.videos) == 1
        assert restored.videos[0].uuid == video.uuid

    def test_roundtrip_with_batches(self):
        session = SessionState(
            staging_path=Path("/tmp/staging"),
            external_path=Path("/Volumes/Archive"),
        )
        batch = session.add_batch(1, ["uuid-1", "uuid-2"])
        batch.exported_uuids = ["uuid-1"]
        batch.completed_at = datetime.now()

        d = session.to_dict()
        restored = SessionState.from_dict(d)
        assert len(restored.batches) == 1
        assert restored.batches[0].batch_number == 1
        assert restored.batches[0].exported_uuids == ["uuid-1"]
        assert restored.batches[0].completed_at is not None


# --- VideoInfo properties ---


class TestVideoInfoProperties:
    def test_size_mb(self):
        video = _make_video(size_bytes=1_048_576)
        assert video.size_mb == 1.0

    def test_size_gb(self):
        video = _make_video(size_bytes=1_073_741_824)
        assert video.size_gb == 1.0

    def test_duration_formatted_minutes(self):
        video = _make_video(duration_seconds=125)
        assert video.duration_formatted == "2:05"

    def test_duration_formatted_hours(self):
        video = _make_video(duration_seconds=3661)
        assert video.duration_formatted == "1:01:01"

    def test_size_formatted(self):
        video = _make_video(size_bytes=2_147_483_648)
        assert video.size_formatted == "2.00 GB"


# --- VideoInfo ML field defaults ---


class TestVideoInfoMLFields:
    def test_default_ml_fields(self):
        video = _make_video()
        assert video.labels == []
        assert video.persons == []
        assert video.face_count == 0
        assert video.aesthetic_score is None
        assert video.ai_description is None
        assert video.relevance_score is None

    def test_ml_fields_roundtrip(self):
        video = _make_video(
            labels=["outdoor", "beach"],
            persons=["Emma"],
            face_count=1,
            aesthetic_score=0.85,
            ai_description="Kids playing at the beach",
            relevance_score=0.92,
        )
        d = video_to_dict(video)
        restored = video_from_dict(d)
        assert restored.labels == ["outdoor", "beach"]
        assert restored.persons == ["Emma"]
        assert restored.face_count == 1
        assert restored.aesthetic_score == 0.85
        assert restored.ai_description == "Kids playing at the beach"
        assert restored.relevance_score == 0.92

    def test_backwards_compat_missing_ml_fields(self):
        """video_from_dict must tolerate dicts without ML fields (old manifests)."""
        old_dict = {
            "uuid": "test-uuid-1",
            "filename": "ABC123.mov",
            "original_filename": "IMG_0001.MOV",
            "date_created": "2024-06-15T14:30:00+00:00",
            "date_modified": "2024-06-15T14:30:00+00:00",
            "size_bytes": 1_073_741_824,
            "duration_seconds": 120.5,
            "width": 1920,
            "height": 1080,
        }
        video = video_from_dict(old_dict)
        assert video.labels == []
        assert video.persons == []
        assert video.face_count == 0
        assert video.aesthetic_score is None


# --- MomentGroup quality methods ---


def _make_moment_with_scores(scores: list[float | None]) -> MomentGroup:
    """Create a MomentGroup with videos having given aesthetic scores."""
    videos = []
    for i, score in enumerate(scores):
        v = _make_video(
            uuid=f"uuid-{i}",
            filename=f"video{i}.mov",
            original_filename=f"IMG_{i:04d}.MOV",
            size_bytes=(i + 1) * 100_000_000,
            aesthetic_score=score,
        )
        videos.append(v)
    return MomentGroup(name="Test Moment", videos=videos)


class TestMomentGroupQuality:
    def test_avg_aesthetic_score_all_scored(self):
        moment = _make_moment_with_scores([0.4, 0.6, 0.8])
        avg = moment.avg_aesthetic_score
        assert avg is not None
        assert abs(avg - 0.6) < 0.001

    def test_avg_aesthetic_score_no_scores(self):
        moment = _make_moment_with_scores([None, None])
        assert moment.avg_aesthetic_score is None

    def test_avg_aesthetic_score_mixed(self):
        moment = _make_moment_with_scores([0.9, None, 0.3])
        avg = moment.avg_aesthetic_score
        assert avg is not None
        assert abs(avg - 0.6) < 0.001

    def test_quality_ranked_candidates_returns_lowest(self):
        # Scores: 0.9, 0.7, 0.5, 0.3 — keep top 2, archive bottom 2
        moment = _make_moment_with_scores([0.9, 0.7, 0.5, 0.3])
        candidates = moment.quality_ranked_candidates(keep_top_n=2)
        assert len(candidates) == 2
        candidate_scores = [v.aesthetic_score for v in candidates]
        assert 0.5 in candidate_scores
        assert 0.3 in candidate_scores

    def test_quality_ranked_candidates_keep_more_than_available(self):
        moment = _make_moment_with_scores([0.8, 0.5])
        candidates = moment.quality_ranked_candidates(keep_top_n=5)
        assert candidates == []

    def test_quality_ranked_candidates_none_scores_treated_as_lowest(self):
        moment = _make_moment_with_scores([0.9, None, 0.5])
        candidates = moment.quality_ranked_candidates(keep_top_n=1)
        # Should keep the 0.9 score; archive 0.5 and None
        assert len(candidates) == 2
        unscored = [v for v in candidates if v.aesthetic_score is None]
        assert len(unscored) == 1
