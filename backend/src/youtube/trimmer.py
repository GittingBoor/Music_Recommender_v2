import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_MUSIC_LABEL = "music"
# The CNN labels drum-only, distorted or effect-heavy intros/outros "noise";
# next to music that is almost always part of the song, so it is kept.
_NOISE_LABEL = "noise"
_MP3_QUALITY = "192"
# Edges shorter than this are kept — a brief misdetection isn't worth a cut.
_MIN_CUT_SECONDS = 2.5

Segment = tuple[str, float, float]


@dataclass(frozen=True)
class MusicSpan:
    """The start/end (seconds) of the actual music within a track."""

    start: float
    end: float


def music_span(segmentation: list[Segment]) -> MusicSpan | None:
    """Return the span to keep from an inaSpeechSegmenter segmentation.

    Keeps everything from the first to the last music segment, widened by
    any noise directly attached to it. Speech and silence at the edges are
    cut, as is noise separated from the music by them (street sounds before
    a talk intro). Edges shorter than ``_MIN_CUT_SECONDS`` are not cut.
    Returns ``None`` when no music is detected.
    """
    segments = [(label, float(start), float(end)) for (label, start, end) in segmentation]
    music = [i for i, (label, _, _) in enumerate(segments) if label == _MUSIC_LABEL]
    if not music:
        return None

    first, last = music[0], music[-1]
    while first > 0 and segments[first - 1][0] == _NOISE_LABEL:
        first -= 1
    while last < len(segments) - 1 and segments[last + 1][0] == _NOISE_LABEL:
        last += 1

    track_start, track_end = segments[0][1], segments[-1][2]
    start, end = segments[first][1], segments[last][2]
    if start - track_start < _MIN_CUT_SECONDS:
        start = track_start
    if track_end - end < _MIN_CUT_SECONDS:
        end = track_end
    return MusicSpan(start=start, end=end)


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
        """Return the span of the song itself (see :func:`music_span`).

        Only the edges are cut — the song stays continuous instead of being
        stitched together from fragments. Returns ``None`` when no music is
        detected.
        """
        return music_span(self._segmenter(str(audio_path)))

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
