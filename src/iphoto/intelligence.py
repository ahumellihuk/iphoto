"""On-device ML index for NL search and video quality analysis.

Requires the [intelligence] optional extras:
    uv sync --extra intelligence

Falls back gracefully if extras are not installed — callers should check
`MLIndex.available()` before use.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import VideoInfo

logger = logging.getLogger(__name__)

_DEPS_AVAILABLE: bool | None = None  # cached after first check


def intelligence_available() -> bool:
    """Return True if all [intelligence] extras are installed."""
    global _DEPS_AVAILABLE
    if _DEPS_AVAILABLE is not None:
        return _DEPS_AVAILABLE
    try:
        import chromadb  # noqa: F401
        import mlx_embeddings  # noqa: F401

        _DEPS_AVAILABLE = True
    except ImportError:
        _DEPS_AVAILABLE = False
    return _DEPS_AVAILABLE


# VLM prompt — ask for a JSON summary so the result is embeddable structured text
_VLM_PROMPT = (
    "Analyze this video thumbnail. Reply with a single JSON object:\n"
    '{"summary": "<one sentence>", "activities": ["<act1>"], "setting": "<indoor/outdoor + context>"}\n'
    "No explanation, just the JSON."
)

_COLLECTION_NAME = "iphoto_videos"
_EMBED_MODEL = "mlx-community/all-MiniLM-L6-v2-4bit"
_VLM_MODEL = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"


class MLIndex:
    """Local ML index backed by ChromaDB + mlx-embeddings.

    Provides:
    - Per-video description embedding (from Apple metadata or VLM analysis)
    - Semantic NL search via cosine similarity
    - Persistent cache: previously analysed videos are not re-processed
    """

    def __init__(self, db_path: Path) -> None:
        if not intelligence_available():
            raise RuntimeError("Intelligence extras not installed. Run: uv sync --extra intelligence")
        import chromadb

        db_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(db_path))
        self._collection = self._client.get_or_create_collection(
            _COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._embed_model = None  # lazy-loaded
        self._vlm_model = None  # lazy-loaded (only with --analyze)
        self._vlm_processor = None
        self._vlm_config = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_indexed(self, uuid: str) -> bool:
        """Return True if this video UUID already has an embedding stored."""
        result = self._collection.get(ids=[uuid], include=[])
        return bool(result["ids"])

    def build_description(self, video: VideoInfo) -> str:
        """Build a searchable text description from Apple metadata (no ML needed)."""
        parts: list[str] = []
        if video.moment_name:
            parts.append(video.moment_name)
        if video.place_name:
            parts.append(video.place_name)
        parts.extend(video.labels)
        parts.extend(video.persons)
        if video.ai_description:
            parts.append(video.ai_description)
        return " ".join(filter(None, parts)) or video.original_filename

    def analyze_video(self, video: VideoInfo, thumb: Path) -> str:
        """Run VLM on a thumbnail to produce a rich text description.

        Downloads mlx-community/Qwen2.5-VL-3B-Instruct-4bit on first call
        (~2 GB, cached in ~/.cache/huggingface/).
        """
        self._ensure_vlm()
        try:
            from mlx_vlm import generate
            from mlx_vlm.prompt_utils import apply_chat_template

            formatted = apply_chat_template(
                self._vlm_processor,
                self._vlm_config,
                _VLM_PROMPT,
                num_images=1,
            )
            raw = generate(
                self._vlm_model,
                self._vlm_processor,
                formatted,
                [str(thumb)],
                max_tokens=150,
                verbose=False,
            )
            # Attempt to extract the summary from the JSON response
            parsed = json.loads(raw.strip())
            summary = parsed.get("summary", "")
            activities = " ".join(parsed.get("activities", []))
            setting = parsed.get("setting", "")
            return " ".join(filter(None, [summary, activities, setting]))
        except Exception as exc:
            logger.debug("VLM analysis failed for %s: %s", video.uuid, exc)
            return self.build_description(video)

    def index_video(self, video: VideoInfo, thumb: Path | None) -> None:
        """Embed a video description and store it in ChromaDB.

        If thumb is provided and VLM is loaded, generates a richer description.
        Otherwise falls back to Apple metadata text.
        """
        if self.is_indexed(video.uuid):
            return

        if thumb and self._vlm_model is not None:
            description = self.analyze_video(video, thumb)
        else:
            description = self.build_description(video)

        embedding = self._embed([description])[0]

        metadata: dict = {
            "uuid": video.uuid,
            "moment_name": video.moment_name or "",
            "place_name": video.place_name or "",
            "aesthetic_score": video.aesthetic_score if video.aesthetic_score is not None else -1.0,
            "face_count": video.face_count,
            "labels": ",".join(video.labels),
            "persons": ",".join(video.persons),
        }
        if description != self.build_description(video):
            # Store VLM description so it can be written back to VideoInfo
            metadata["ai_description"] = description

        self._collection.add(
            ids=[video.uuid],
            embeddings=[embedding],
            documents=[description],
            metadatas=[metadata],
        )

    def query(self, text: str, videos: list[VideoInfo]) -> list[tuple[VideoInfo, float]]:
        """Return videos ranked by semantic similarity to text query.

        Only videos present in the `videos` list are considered (in-library filter).
        Scores are 0.0-1.0 (1.0 = perfect match under cosine distance space).
        """
        if not videos:
            return []

        query_embedding = self._embed([text])[0]
        uuid_set = {v.uuid for v in videos}

        # Query up to all indexed videos for the given UUIDs
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(len(videos), self._collection.count() or 1),
            where=None,
            include=["distances", "metadatas"],
        )

        # ChromaDB cosine space: distance = 1 - similarity, so similarity = 1 - distance
        scored: dict[str, float] = {}
        for uid, dist in zip(results["ids"][0], results["distances"][0], strict=False):
            if uid in uuid_set:
                scored[uid] = max(0.0, 1.0 - dist)

        video_map = {v.uuid: v for v in videos}
        ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)
        return [(video_map[uid], score) for uid, score in ranked if uid in video_map]

    def apply_ai_descriptions(self, videos: list[VideoInfo]) -> None:
        """Write back ai_description from the index into VideoInfo objects."""
        if not videos:
            return
        uuids = [v.uuid for v in videos]
        result = self._collection.get(ids=uuids, include=["metadatas"])
        desc_map = {
            uid: meta.get("ai_description", "")
            for uid, meta in zip(result["ids"], result["metadatas"], strict=False)
            if meta.get("ai_description")
        }
        for video in videos:
            if video.uuid in desc_map:
                video.ai_description = desc_map[video.uuid]

    def close(self) -> None:
        """No-op — ChromaDB PersistentClient flushes automatically."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_embed_model(self) -> None:
        if self._embed_model is None:
            from mlx_embeddings import load_embedding_model

            self._embed_model = load_embedding_model(_EMBED_MODEL)

    def _ensure_vlm(self) -> None:
        if self._vlm_model is None:
            from mlx_vlm import load
            from mlx_vlm.utils import load_config

            self._vlm_model, self._vlm_processor = load(_VLM_MODEL)
            self._vlm_config = load_config(_VLM_MODEL)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        self._ensure_embed_model()
        result = self._embed_model.embed(texts)
        # mlx-embeddings returns list[list[float]] or similar
        if hasattr(result, "tolist"):
            return result.tolist()
        return [list(r) if hasattr(r, "tolist") else r for r in result]
