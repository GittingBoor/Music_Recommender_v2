from src.youtube.trimmer import MusicSpan, music_span


def test_noise_intro_attached_to_music_is_kept() -> None:
    # Real segmentation of PBHdYm98BHY: the song's intro is labelled noise.
    segmentation = [
        ("noise", 0.0, 7.36),
        ("music", 7.36, 45.38),
        ("speech", 45.38, 49.76),
        ("music", 49.76, 125.4),
        ("speech", 125.4, 128.8),
        ("music", 128.8, 144.88),
        ("noEnergy", 144.88, 146.86),
    ]

    assert music_span(segmentation) == MusicSpan(start=0.0, end=146.86)


def test_talk_intro_and_outro_are_cut() -> None:
    segmentation = [
        ("speech", 0.0, 12.0),
        ("music", 12.0, 200.0),
        ("speech", 200.0, 230.0),
    ]

    assert music_span(segmentation) == MusicSpan(start=12.0, end=200.0)


def test_noise_separated_from_music_by_talk_is_cut() -> None:
    segmentation = [
        ("noise", 0.0, 5.0),
        ("speech", 5.0, 15.0),
        ("noise", 15.0, 18.0),
        ("music", 18.0, 200.0),
        ("noEnergy", 200.0, 210.0),
    ]

    assert music_span(segmentation) == MusicSpan(start=15.0, end=200.0)


def test_short_edges_are_not_cut() -> None:
    segmentation = [
        ("speech", 0.0, 1.5),
        ("music", 1.5, 180.0),
        ("noEnergy", 180.0, 181.0),
    ]

    assert music_span(segmentation) == MusicSpan(start=0.0, end=181.0)


def test_no_music_returns_none() -> None:
    assert music_span([("speech", 0.0, 30.0), ("noise", 30.0, 40.0)]) is None
