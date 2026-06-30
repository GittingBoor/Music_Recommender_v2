import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_MUSIC_LABEL = "music"
_MP3_QUALITY = "192"


@dataclass(frozen=True)
class MusicSpan:
    """The start/end (seconds) of the actual music within a track."""

    start: float
    end: float


class MusicTrimmer:
    """Detect the music region of an audio file via inaSpeechSegmenter (CNN)
    and cut away non-music intros/outros (talking, silence, noise).

    The model is loaded lazily on construction, so build this only once and
    reuse it (see :func:`get_music_trimmer`).
    """

    def __init__(self) -> None:
        from inaSpeechSegmenter import Segmenter
        self._segmenter = Segmenter(detect_gender=False)

    def find_music_span(self, audio_path: Path) -> MusicSpan | None:
        """Return the span from the first to the last music segment.

        Trimming to first-music → last-music keeps the song continuous
        instead of stitching fragments together. Returns ``None`` when no
        music is detected.
        """
        segmentation = self._segmenter(str(audio_path))
        music = [
            (float(start), float(end))
            for (label, start, end) in segmentation
            if label == _MUSIC_LABEL
        ]
        if not music:
            return None
        return MusicSpan(start=music[0][0], end=music[-1][1])

    def trim_to(self, src: Path, dest: Path) -> bool:
        """Write the detected music span of ``src`` to ``dest`` as MP3.

        Returns True if a music span was found and written, False otherwise
        (caller should then fall back to the untrimmed file).
        """
        span = self.find_music_span(src)
        if span is None:
            logger.warning("[Trim] No music detected in %s — keeping untrimmed", src.name)
            return False

        dest.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(src),
                "-ss", str(span.start),
                "-to", str(span.end),
                "-b:a", f"{_MP3_QUALITY}k",
                str(dest),
            ],
            capture_output=True,
        )
        if proc.returncode != 0:
            logger.error("[Trim] ffmpeg failed for %s: %s", src.name, proc.stderr.decode(errors="ignore"))
            return False

        logger.info("[Trim] %s -> music span %.1fs–%.1fs", src.name, span.start, span.end)
        return True


_trimmer: MusicTrimmer | None = None


def get_music_trimmer() -> MusicTrimmer:
    """Return a process-wide :class:`MusicTrimmer`, loading the model once."""
    global _trimmer
    if _trimmer is None:
        _trimmer = MusicTrimmer()
    return _trimmer
