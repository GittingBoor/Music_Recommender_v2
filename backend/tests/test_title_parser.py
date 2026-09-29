from src.youtube.title_parser import ParsedTrack, parse_video_title


def test_artist_dash_title_with_noise():
    assert parse_video_title("Avicii - Hey Brother (Official Video)", "AviciiOfficialVEVO") == ParsedTrack(
        title="Hey Brother", artist="Avicii"
    )


def test_topic_channel_is_the_artist():
    assert parse_video_title("Hey Brother", "Avicii - Topic") == ParsedTrack(title="Hey Brother", artist="Avicii")


def test_topic_channel_keeps_dash_in_title():
    assert parse_video_title("Wake Me Up - Radio Edit", "Avicii - Topic") == ParsedTrack(
        title="Wake Me Up - Radio Edit", artist="Avicii"
    )


def test_vevo_channel_without_separator():
    assert parse_video_title("Hello (Official Music Video)", "AdeleVEVO") == ParsedTrack(title="Hello", artist="Adele")


def test_meaningful_brackets_are_kept():
    parsed = parse_video_title("Avicii vs Nicky Romero - I Could Be The One [Radio Edit]", None)
    assert parsed == ParsedTrack(title="I Could Be The One [Radio Edit]", artist="Avicii vs Nicky Romero")


def test_featured_artists_are_dropped():
    assert parse_video_title("David Guetta feat. Kid Cudi - Memories (Lyrics)", None) == ParsedTrack(
        title="Memories", artist="David Guetta"
    )
    assert parse_video_title("Jason Derulo - Talk Dirty ft. 2 Chainz [Official Video]", None) == ParsedTrack(
        title="Talk Dirty", artist="Jason Derulo"
    )


def test_quotes_and_unbracketed_noise():
    assert parse_video_title('Queen – "Bohemian Rhapsody" Official Video', None) == ParsedTrack(
        title="Bohemian Rhapsody", artist="Queen"
    )


def test_unbracketed_live_suffix_and_quality_tags_are_dropped():
    assert parse_video_title("Metallica - Enter Sandman Live Moscow 1991 HD", "Met4life1995") == ParsedTrack(
        title="Enter Sandman", artist="Metallica"
    )
    assert parse_video_title("Bob Marley - Could You Be Loved (Video) HD", "William Marley") == ParsedTrack(
        title="Could You Be Loved", artist="Bob Marley"
    )


def test_bracketed_and_dashed_live_markers_are_dropped():
    assert parse_video_title("Nirvana - Smells Like Teen Spirit (Live at Reading 1992)", "Nirvana") == ParsedTrack(
        title="Smells Like Teen Spirit", artist="Nirvana"
    )
    assert parse_video_title("Wake Me Up - Live", "Avicii - Topic") == ParsedTrack(title="Wake Me Up", artist="Avicii")


def test_live_as_part_of_the_song_title_is_kept():
    assert parse_video_title("Oasis - Live Forever (Live at Knebworth)", None) == ParsedTrack(
        title="Live Forever", artist="Oasis"
    )
    assert parse_video_title("Taylor Swift - Long Live", None) == ParsedTrack(title="Long Live", artist="Taylor Swift")


def test_colon_separates_artist_and_title():
    assert parse_video_title("Metallica: Enter Sandman (Official Music Video)", "Metallica") == ParsedTrack(
        title="Enter Sandman", artist="Metallica"
    )


def test_colon_suffix_on_the_artist_part_is_dropped():
    assert parse_video_title("Rammstein: Paris - Du Hast (Official Video)", "Rammstein Official") == ParsedTrack(
        title="Du Hast", artist="Rammstein"
    )


def test_unreadable_title_returns_none():
    assert parse_video_title("(Official Video)", None) is None
