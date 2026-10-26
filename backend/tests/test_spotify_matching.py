from src.spotify.matching import (
    SpotifyTrack, artist_channel, candidate_fits, identity_matches, order_candidates, trusted_upload,
)


def _track(title: str, *artists: str, seconds: int | None = 200) -> SpotifyTrack:
    duration_ms = seconds * 1000 if seconds is not None else None
    return SpotifyTrack(spotify_id="id", title=title, artists=artists, duration_ms=duration_ms, isrc=None)


# --- query --------------------------------------------------------------------

def test_query_uses_primary_artist_and_plain_title() -> None:
    track = _track("Here Comes The Sun - Remastered 2009", "The Beatles")
    assert track.query == "The Beatles - Here Comes The Sun"
    assert _track("Stay (feat. Justin Bieber)", "The Kid LAROI", "Justin Bieber").query == "The Kid LAROI - Stay"


# --- candidate_fits ------------------------------------------------------------

def test_candidate_accepts_topic_upload() -> None:
    track = _track("Blinding Lights", "The Weeknd")
    assert candidate_fits(track, "Blinding Lights", "The Weeknd - Topic", 201)


def test_candidate_accepts_music_video_with_intro() -> None:
    track = _track("Hey Brother", "Avicii", seconds=200)
    assert candidate_fits(track, "Avicii - Hey Brother (Official Video)", "AviciiOfficialVEVO", 240)


def test_candidate_accepts_small_deviation_in_both_directions() -> None:
    track = _track("Hey Brother", "Avicii", seconds=200)
    assert candidate_fits(track, "Avicii - Hey Brother", "Avicii", 186)
    assert candidate_fits(track, "Avicii - Hey Brother", "Avicii", 214)


def test_candidate_rejects_too_long() -> None:
    track = _track("Hey Brother", "Avicii", seconds=200)
    assert not candidate_fits(track, "Avicii - Hey Brother (Official Video)", "Avicii", 300)
    assert not candidate_fits(track, "Avicii - Hey Brother", "Avicii", 170)


def test_candidate_rejects_unknown_video_length() -> None:
    assert not candidate_fits(_track("Hey Brother", "Avicii"), "Avicii - Hey Brother", "Avicii", None)


def test_candidate_without_track_length_ignores_length() -> None:
    assert candidate_fits(_track("Hey Brother", "Avicii", seconds=None), "Avicii - Hey Brother", "Avicii", 999)


def test_candidate_rejects_live_and_cover() -> None:
    track = _track("Wonderwall", "Oasis", seconds=258)
    assert not candidate_fits(track, "Oasis - Wonderwall (Live at Knebworth)", "Oasis", 260)
    assert not candidate_fits(track, "Wonderwall - Oasis (Acoustic Cover)", "Some Singer", 258)
    assert not candidate_fits(track, "Oasis - Wonderwall (Remix)", "Oasis", 258)


def test_candidate_allows_version_word_named_by_track() -> None:
    track = _track("Wonderwall - Live", "Oasis", seconds=258)
    assert candidate_fits(track, "Oasis - Wonderwall (Live)", "Oasis", 260)
    remix = _track("Titanium - Alesso Remix", "David Guetta", "Sia", seconds=250)
    assert candidate_fits(remix, "David Guetta - Titanium (Alesso Remix)", "David Guetta", 250)


def test_candidate_rejects_other_artist() -> None:
    track = _track("Hello", "Adele", seconds=295)
    assert not candidate_fits(track, "Lionel Richie - Hello", "LionelRichieVEVO", 295)


def test_candidate_rejects_other_song_of_same_artist() -> None:
    track = _track("Hello", "Adele", seconds=295)
    assert not candidate_fits(track, "Adele - Skyfall", "Adele", 290)


def test_candidate_accepts_featured_artist_channel() -> None:
    track = _track("Stay", "The Kid LAROI", "Justin Bieber", seconds=141)
    assert candidate_fits(track, "Stay", "Justin Bieber - Topic", 141)


def test_candidate_accepts_accents() -> None:
    track = _track("Déjà Vu", "Beyoncé", "JAY-Z", seconds=240)
    assert candidate_fits(track, "Beyonce - Deja Vu ft. Jay-Z", "beyonceVEVO", 260)


# --- identity_matches ----------------------------------------------------------

def test_identity_ignores_version_markers() -> None:
    track = _track("Here Comes The Sun - Remastered 2009", "The Beatles")
    assert identity_matches(track, "Here Comes the Sun", "The Beatles")


def test_identity_accepts_any_spotify_artist() -> None:
    track = _track("Stay", "The Kid LAROI", "Justin Bieber")
    assert identity_matches(track, "Stay", "Justin Bieber")
    assert identity_matches(track, "Stay", "The Kid LAROI & Justin Bieber")


def test_identity_rejects_other_song() -> None:
    track = _track("Hello", "Adele")
    assert not identity_matches(track, "Hello", "Lionel Richie")
    assert not identity_matches(track, "Skyfall", "Adele")
    assert not identity_matches(track, "Hello Hello", "Adele")


def test_identity_handles_feat_in_title() -> None:
    track = _track("Lean On (feat. MØ & DJ Snake)", "Major Lazer", "MØ", "DJ Snake")
    assert identity_matches(track, "Lean On", "Major Lazer feat. MØ & DJ Snake")


def test_identity_tolerates_spelling_and_punctuation() -> None:
    track = _track("Don't Stop Me Now - Remastered 2011", "Queen")
    assert identity_matches(track, "Don’t Stop Me Now", "Queen")
    assert identity_matches(_track("Sweet Child O' Mine", "Guns N' Roses"), "Sweet Child o’ Mine", "Guns N’ Roses")


# --- found in a dry run against real YouTube results ---------------------------

def test_candidate_rejects_foreign_featured_artist() -> None:
    track = _track("Titanium (feat. Sia)", "David Guetta", "Sia", seconds=245)
    assert not candidate_fits(track, "David Guetta - Titanium ft. Che'Nelle", "David Guetta", 232)
    assert candidate_fits(track, "David Guetta - Titanium ft. Sia (Official Video)", "David Guetta", 246)


def test_candidate_accepts_featured_artist_spelled_differently() -> None:
    track = _track("Deja Vu (feat. JAŸ-Z)", "Beyoncé", "JAŸ-Z", seconds=239)
    assert candidate_fits(track, "Beyonce Ft. Jay Z - Deja Vu (Lyrics)", "Infinite Music", 244)


def test_candidate_rejects_alternate_takes_and_demos() -> None:
    track = _track("Here Comes The Sun - Remastered 2009", "The Beatles", seconds=185)
    assert not candidate_fits(track, "Here Comes The Sun (Take 9)", "The Beatles", 200)
    assert not candidate_fits(track, "Here Comes The Sun (Demo)", "The Beatles", 190)


def test_order_prefers_topic_then_closest_length() -> None:
    track = _track("Sweet Child O' Mine", "Guns N' Roses", seconds=356)
    live = ("Guns N Roses: Sweet Child O' Mine in Dublin", "Guns N' Roses", 372)
    reupload = ("Guns N' Roses Sweet Child O' Mine l MP3", "WiChonWichi", 355)
    topic = ("Sweet Child O' Mine", "Guns N' Roses - Topic", 359)
    ordered = order_candidates(track, [live, reupload, topic], key=lambda h: (h[0], h[1], h[2]))
    assert ordered == [topic, reupload, live]


# --- final review fixes -----------------------------------------------------------

def test_identity_rejects_other_part_or_number() -> None:
    assert not identity_matches(_track("Part I", "Band"), "Part II", "Band")
    assert not identity_matches(_track("Track 1", "Band"), "Track 2", "Band")
    assert not identity_matches(_track("Hello", "Adele"), "Hell", "Adele")


def test_identity_splits_spotify_artist_credit() -> None:
    assert identity_matches(_track("Song", "Alpha & Beta"), "Song", "Alpha")
    assert identity_matches(_track("The Boxer", "Simon & Garfunkel"), "The Boxer", "Simon & Garfunkel")


def test_trusted_upload_accepts_topic_and_artist_channel() -> None:
    hello = _track("Hello", "Adele", seconds=295)
    assert trusted_upload(hello, "Hello", "Adele - Topic")
    assert trusted_upload(hello, "Adele - Hello (Official Music Video)", "AdeleVEVO")
    assert trusted_upload(_track("Lean On (feat. MØ & DJ Snake)", "Major Lazer", "MØ", "DJ Snake"),
                          "Major Lazer & DJ Snake - Lean On (feat. MØ) [Official 4K Music Video]", "Major Lazer Official")


def test_trusted_upload_rejects_foreign_channel_and_extra_words() -> None:
    hello = _track("Hello", "Adele", seconds=295)
    assert not trusted_upload(hello, "Hello - Adele | Drum Cam", "DrumGuy")
    assert not trusted_upload(hello, "Adele - Hello", "Some Fan")
    assert not trusted_upload(hello, "Adele - Hello (Official Music Video) [Reprise]", "Adele")
    assert not trusted_upload(_track("Song", "Blur"), "Blur - Song 2 (Official Video)", "Blur")
    assert not trusted_upload(_track("Intro", "The xx"), "The xx - Intro (Extended)", "The xx")
    assert not trusted_upload(_track("Run", "Foo Fighters"), "Foo Fighters - Run (Audio) - Rock Am Ring", "Foo Fighters")


def test_candidate_accepts_remastered_version_upload() -> None:
    track = _track("Wonderwall - Remastered", "Oasis", seconds=258)
    assert candidate_fits(track, "Oasis - Wonderwall (Remastered Version)", "Oasis", 259)


def test_trusted_upload_handles_official_channel_suffix_and_animated_video() -> None:
    assert trusted_upload(_track("Atemlos durch die Nacht", "Helene Fischer"),
                          "Helene Fischer - Atemlos durch die Nacht", "Helene Fischer (Official)")
    assert trusted_upload(_track("Levitating (feat. DaBaby)", "Dua Lipa", "DaBaby"),
                          "Dua Lipa - Levitating (Official Animated Music Video)", "Dua Lipa")


# --- playlist import misses (2026-10-26) ----------------------------------------------

def test_candidate_ignores_extra_title_parts_without_version_words() -> None:
    assert candidate_fits(_track("Deja Vu (Initial D)", "Tsuko G.", seconds=250), "Deja Vu", "Tsuko G. - Topic", 251)
    assert candidate_fits(_track("Whatever - +1", "CRO", seconds=191), "Whatever", "CRO - Topic", 191)
    assert candidate_fits(_track("Medieval - Spotify Singles", "FINNEAS", seconds=190), "Medieval", "FINNEAS - Topic", 190)


def test_candidate_keeps_extra_title_parts_that_name_a_version() -> None:
    assert not candidate_fits(_track("Heart Attack - Rock Version", "Demi Lovato", seconds=239),
                              "Heart Attack", "Demi Lovato - Topic", 211)
    assert not candidate_fits(_track("DEADBEAT - demo", "WesGhost", seconds=145), "DEADBEAT", "WesGhost - Topic", 145)
    assert not candidate_fits(_track("EISKALT RMX", "Culcha Candela", seconds=128), "EISKALT", "Culcha Candela - Topic", 128)


def test_identity_ignores_extra_title_parts() -> None:
    assert identity_matches(_track("Deja Vu (Initial D)", "Tsuko G."), "Deja Vu", "Tsuko G.")
    assert identity_matches(_track("Call Me, Beep Me! (The Kim Possible Song)", "Crystal Rock"), "Call Me, Beep Me!", "Crystal Rock")


def test_dollar_sign_spells_s() -> None:
    assert identity_matches(_track("Die Young", "Kesha"), "Die Young", "Ke$ha")
    assert candidate_fits(_track("Die Young", "Kesha", seconds=211), "Die Young", "Ke$ha - Topic", 212)


def test_trusted_upload_accepts_german_official_video() -> None:
    assert trusted_upload(_track("Westkreuz", "Von Wegen Lisbeth"),
                          "Von Wegen Lisbeth - Westkreuz (Offizielles Video)", "Von Wegen Lisbeth")
    assert trusted_upload(_track("Westkreuz", "Von Wegen Lisbeth"),
                          "Von Wegen Lisbeth - Westkreuz (Offizielles Musikvideo)", "Von Wegen Lisbeth")


def test_artist_channel() -> None:
    hello = _track("Hello", "Adele")
    assert artist_channel(hello, "Adele - Topic")
    assert artist_channel(hello, "AdeleVEVO")
    assert artist_channel(_track("Mission", "Ely Oaks", "joki"), "joki")
    assert not artist_channel(hello, "Some Fan")
    assert not artist_channel(hello, None)
