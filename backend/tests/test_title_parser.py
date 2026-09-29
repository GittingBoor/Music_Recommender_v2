from src.youtube.title_parser import (
    ParsedTrack,
    guess_track,
    parse_search_query,
    parse_video_title,
    video_names_artist,
)


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


def test_from_brackets_symbols_frequencies_and_hashtags_are_dropped():
    assert parse_video_title(
        "Simon & Garfunkel - The Sound of Silence (from The Concert in Central Park)", "Simon & Garfunkel"
    ) == ParsedTrack(title="The Sound of Silence", artist="Simon & Garfunkel")
    assert parse_video_title("Beethoven - Moonlight Sonata ⚪ 432 Hz", "Moonlight Sonata") == ParsedTrack(
        title="Moonlight Sonata", artist="Beethoven"
    )
    assert parse_video_title("Hans Zimmer - Time (#EnterTheWorldOfHansZimmer B)", "Hans Zimmer") == ParsedTrack(
        title="Time", artist="Hans Zimmer"
    )


def test_video_names_its_artist_only_with_a_separator_or_an_artist_channel():
    assert video_names_artist("Nirvana - Smells Like Teen Spirit", "Nirvana")
    assert video_names_artist("Hey Brother", "Avicii - Topic")
    assert video_names_artist("Hello (Official Music Video)", "AdeleVEVO")
    assert not video_names_artist('Beethoven "Moonlight" Sonata, III Presto', "Valentina Lisitsa QOR Records Official channel")


def test_search_query_is_read_as_artist_and_title():
    assert parse_search_query("Beethoven - Moonlight Sonata") == ParsedTrack(title="Moonlight Sonata", artist="Beethoven")
    assert parse_search_query("Deichkind - Remmidemmi official audio") == ParsedTrack(title="Remmidemmi", artist="Deichkind")
    assert parse_search_query("moonlight sonata") is None


def test_name_guess_uses_the_query_only_when_the_video_does_not_name_the_artist():
    lisitsa = ('Beethoven "Moonlight" Sonata, III Presto', "Valentina Lisitsa QOR Records Official channel")
    assert guess_track(*lisitsa, "Beethoven - Moonlight Sonata") == ParsedTrack(title="Moonlight Sonata", artist="Beethoven")
    assert guess_track("Nirvana - Smells Like Teen Spirit", "Nirvana", "nirvana teen spirit") == ParsedTrack(
        title="Smells Like Teen Spirit", artist="Nirvana"
    )
    assert guess_track(*lisitsa, None) == parse_video_title(*lisitsa)


def test_title_first_videos_are_recognised_by_the_channel():
    assert parse_video_title("In The End [Official HD Music Video] - Linkin Park", "Linkin Park") == ParsedTrack(
        title="In The End", artist="Linkin Park"
    )


def test_topic_title_mentioning_a_composer_keeps_the_mention():
    parsed = parse_video_title(
        "Tchaikovsky: Swan Lake, Op. 20, Act II: No. 10, Scene. Moderato", "Orchestre symphonique de Montréal - Topic"
    )
    assert parsed is not None
    assert parsed.artist == "Orchestre symphonique de Montréal"
    assert parsed.mentioned_artist == "Tchaikovsky"


def test_topic_title_repeating_the_artist_loses_the_prefix():
    assert parse_video_title("Adele - Hello", "Adele - Topic") == ParsedTrack(title="Hello", artist="Adele")


def test_title_repeating_one_of_the_artists_before_a_colon_loses_it():
    parsed = parse_video_title(
        "Khatia Buniatishvili, Erik Satie - Erik Satie: Gymnopédie No.1", "Khatia Buniatishvili official"
    )
    assert parsed == ParsedTrack(title="Gymnopédie No.1", artist="Khatia Buniatishvili, Erik Satie")
