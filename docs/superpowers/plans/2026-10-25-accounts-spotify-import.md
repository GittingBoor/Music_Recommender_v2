# Accounts + Spotify-Playlist-Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nutzer-Accounts (Login oben rechts, Passwort-Reset per Brevo), Spotify-Verbindung pro Account und Ein-Klick-Import eigener Playlists über die YouTube-Pipeline, ohne falsche Songs in der Datenbank.

**Architecture:** Neue Backend-Pakete `src/accounts` (Nutzer, Session, Reset, Mail) und `src/spotify` (OAuth-Client, Abgleich, Importer). Der Import nutzt die bestehende Bulk-Warteschlange (`src/ingest/bulk.py`) mit einem *erwarteten Track*. `process_audio_file` lehnt Audio ab, das AcoustID als anderen Song erkennt. Das Frontend bekommt Account-Seiten und einen Spotify-Abschnitt auf der Upload-Seite.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, stdlib `urllib`/`hashlib` (keine neuen Python-Abhängigkeiten), React + TypeScript + Tailwind.

**Spec:** `docs/superpowers/specs/2026-10-25-accounts-spotify-import-design.md`

## Global Constraints

- Keine neuen Python-Abhängigkeiten. HTTP über `urllib`, Hashing über `hashlib.scrypt` (`src/auth/password.py`).
- Die Vorab-Passwortseite (`/login`, `mr_session`, `nginx auth_request`) bleibt unverändert.
- Ohne Account funktioniert alles wie bisher. Kein bestehender Endpoint verlangt einen Account.
- Nutzer-Cookie `mr_user`, httponly, `secure=settings.session_cookie_secure`, samesite=lax.
- Reset-Link: `{settings.public_base_url}/reset-password/<token>` (Token im Pfad), gültig 1 h, einmalig.
- Spotify-Scopes: `playlist-read-private playlist-read-collaborative`. Redirect-URI aus `SPOTIFY_REDIRECT_URI`.
- Nur Playlists, deren `owner.id == spotify_user_id` oder `collaborative == true`.
- Längentoleranz: `abs(video - track) <= 15 s` oder `track <= video <= track * 1.25`.
- Höchstens 3 YouTube-Kandidaten pro Track.
- UI-Texte auf Deutsch, Navigation bleibt englisch. UI über Agent `webbuilder` + Skill `impeccable`.
- Commits ohne jede Erwähnung von Claude/AI.

## Review Focus

- E-Mail mit Großbuchstaben/Leerzeichen bei Registrierung vs. Login → derselbe Account (`test_email_is_normalised`).
- Spotify-Track mit mehreren Künstlern, AcoustID nennt nur einen davon → zählt als Treffer (`test_identity_accepts_any_spotify_artist`).
- Spotify-Titel „Song - Remastered 2011“ vs. AcoustID „Song“ → Treffer. „Song (Live)“ auf Spotify vs. Live-Video → Kandidat erlaubt (`test_identity_ignores_version_markers`, `test_candidate_allows_version_word_named_by_track`).
- Abgelaufener Spotify-Access-Token mitten im Import → Refresh, kein Abbruch (`test_client_refreshes_expired_token`).
- Backend-Neustart während des Imports → `queued`-Tracks werden wieder eingereiht (`test_resume_requeues_queued_tracks`).

---

### Task 1: Konfiguration, Modelle, Migration

**Files:**
- Modify: `backend/src/core/config.py` (Settings)
- Modify: `backend/src/metadata/identity.py` (`MetadataSource.SPOTIFY = "spotify"`)
- Create: `backend/src/db/models/account.py` (`User`, `PasswordResetToken`, `SpotifyConnection`)
- Create: `backend/src/db/models/playlist_import.py` (`PlaylistImport`, `PlaylistImportTrack`)
- Modify: `backend/src/db/models/__init__.py`
- Create: `backend/alembic/versions/b3c4d5e6f7a8_add_accounts_and_playlist_imports.py` (down_revision `a2b3c4d5e6f7`)
- Modify: `backend/.env.example`

**Interfaces:**
- Produces: Settings `spotify_redirect_uri: str = ""`, `public_base_url: str = "http://127.0.0.1:5173"`, `brevo_api_key: str = ""`, `mail_from: str = ""`, `mail_from_name: str = "Music Recommender"`, `user_session_days: int = 90`.
- Produces Tabellen/Spalten wie in der Spec. `PlaylistImportTrack.status: str` (`queued|saved|duplicate|failed`), `artists: str` (JSON-Liste), `duration_ms: int | None`, `isrc: str | None`, `reason: str | None`, `song_id: str | None`, `video_id: str | None`, Index auf `(import_id, position)` und auf `status`.

- [ ] Step 1: Settings, Enum, Modelle, Migration schreiben.
- [ ] Step 2: `docker exec music_recommender_v2-backend-1 alembic upgrade head`. Erwartet: ohne Fehler, `alembic current` = `b3c4d5e6f7a8`.
- [ ] Step 3: `python -m pytest -q` grün. Commit.

### Task 2: Account-Kern (Passwort, Session, Reset-Token, Mail)

**Files:**
- Create: `backend/src/accounts/__init__.py`, `backend/src/accounts/session.py`, `backend/src/accounts/reset.py`, `backend/src/accounts/mailer.py`
- Test: `backend/tests/test_accounts_core.py`

**Interfaces:**
- Produces `UserSessionSigner(secret: bytes, lifetime: timedelta)` mit `issue(user_id: int, password_hash: str, now: datetime) -> str` und `user_id(token: str, password_hash_of: Callable[[int], str | None], now: datetime) -> int | None`. Token `<user_id>.<expiry>.<hmac>`, HMAC über `user_id.expiry` mit Schlüssel `hmac(secret, password_hash)`.
- Produces `new_reset_token() -> tuple[str, str]` (Klartext, sha256-hex) und `hash_reset_token(token: str) -> str`.
- Produces `normalise_email(raw: str) -> str` (strip + lower) und `is_valid_email(email: str) -> bool` (ein `@`, Punkt in der Domain, ≤ 254 Zeichen).
- Produces `class Mailer(Protocol): def send(self, to: str, subject: str, text: str) -> None`, `BrevoMailer(api_key, sender, sender_name)` (POST `https://api.brevo.com/v3/smtp/email`, wirft `MailDeliveryError` bei HTTP-Fehler), `LogMailer` (loggt Warnung mit Inhalt), `get_mailer() -> Mailer` (Brevo, wenn Key und Absender gesetzt).

- [ ] Step 1: Tests: `test_user_token_roundtrip`, `test_user_token_invalid_after_password_change`, `test_user_token_expires`, `test_reset_token_hash_matches`, `test_email_is_normalised` (`"  Foo@Bar.DE "` → `"foo@bar.de"`), `test_email_validation`, `test_brevo_payload` (urlopen gepatcht: Header `api-key`, JSON mit `sender.email`, `to[0].email`, `subject`, `textContent`).
- [ ] Step 2: Tests laufen lassen → FAIL (Import fehlt).
- [ ] Step 3: Implementieren.
- [ ] Step 4: Tests grün. Commit.

### Task 3: Account-Routen

**Files:**
- Create: `backend/src/api/routes/account.py`, Modify: `backend/src/main.py`
- Create: `backend/src/api/user.py` (Dependencies)
- Test: `backend/tests/test_account_routes.py`

**Interfaces:**
- Consumes Task 1–2.
- Produces Dependencies `current_user(request, db) -> User | None` und `require_user(...) -> User` (401 `"Not logged in"`).
- Routen (alle JSON, Fehlermeldungen auf Deutsch im `detail`):
  - `POST /api/account/register {email, password}` → 201 `AccountOut{email, spotify: SpotifyStatusOut | None}` + Cookie. Passwort 8–256 Zeichen. 409 bei vorhandener E-Mail, 422 bei ungültiger E-Mail.
  - `POST /api/account/login {email, password}` → 200 `AccountOut` + Cookie, 401 `"E-Mail oder Passwort falsch"`.
  - `POST /api/account/logout` → 204, Cookie gelöscht.
  - `GET /api/account/me` → 200 `AccountOut` oder 401.
  - `POST /api/account/forgot-password {email}` → immer 204. Für ein existierendes Konto wird ein Token gespeichert und eine Mail mit dem Link verschickt. Ein Mail-Fehler wird geloggt und nicht an den Client gegeben.
  - `POST /api/account/reset-password {token, password}` → 204, setzt neues Passwort, markiert Token als benutzt, setzt neues Cookie. 400 `"Link ungültig oder abgelaufen"`.
- `SpotifyStatusOut{display_name: str | None, spotify_user_id: str}`.

- [ ] Step 1: Tests mit SQLite-in-memory-Session für die neuen Tabellen (nur `User`, `PasswordResetToken`, `SpotifyConnection` per `Base.metadata.create_all(tables=[...])`) und einem `FakeMailer`, der Mails sammelt: `test_register_then_me`, `test_register_duplicate_email_409`, `test_login_wrong_password_401`, `test_forgot_unknown_email_still_204_no_mail`, `test_reset_flow_changes_password_and_invalidates_old_cookie`, `test_reset_token_single_use`, `test_reset_token_expired`.
- [ ] Step 2: FAIL. Step 3: Implementieren, Router in `main.py`. Step 4: grün. Commit.

### Task 4: Abgleich Spotify-Track ↔ YouTube/AcoustID

**Files:**
- Create: `backend/src/spotify/__init__.py`, `backend/src/spotify/matching.py`
- Test: `backend/tests/test_spotify_matching.py`

**Interfaces:**
- Produces `@dataclass(frozen=True) SpotifyTrack(spotify_id: str, title: str, artists: tuple[str, ...], duration_ms: int | None, isrc: str | None)` mit `query -> str` (`"<artists[0]> - <title ohne Versionsmarker>"`) und `primary_artist -> str`.
- Produces `candidate_fits(track: SpotifyTrack, video_title: str, uploader: str | None, duration_s: int | None) -> bool`: alle Wörter des Titels (normalisiert, ohne Versionsmarker und `feat.`-Klammern) im Video-Titel, ein Spotify-Künstler im Video-Titel oder Kanal (ohne „- Topic“/„VEVO“), Länge in Toleranz (fehlende Länge → False), kein Versionswort aus `ranking._VERSION_WORDS`, das nicht auch im Spotify-Titel steht.
- Produces `identity_matches(track: SpotifyTrack, title: str, artist: str) -> bool`: Titel nach `strip_version_markers` + Normalisierung gleich oder `title_similar(..., 0.85)`, und irgendein Spotify-Künstler gleich einem Künstler aus `split_artist_featuring(artist)`.

- [ ] Step 1: Tests: `test_candidate_accepts_topic_upload`, `test_candidate_accepts_music_video_with_intro` (Track 200 s, Video 240 s), `test_candidate_rejects_too_long` (Video 300 s), `test_candidate_rejects_live_and_cover`, `test_candidate_allows_version_word_named_by_track`, `test_candidate_rejects_other_artist`, `test_candidate_accepts_accents` („Beyoncé“ vs. „Beyonce“), `test_identity_ignores_version_markers`, `test_identity_accepts_any_spotify_artist`, `test_identity_rejects_other_song`, `test_identity_handles_feat_in_title` („Song (feat. X)“ vs. „Song“).
- [ ] Step 2: FAIL. Step 3: Implementieren. Step 4: grün. Commit.

### Task 5: Spotify-Client (OAuth, Playlists, Tracks)

**Files:**
- Create: `backend/src/spotify/client.py`
- Test: `backend/tests/test_spotify_client.py`

**Interfaces:**
- Produces `SpotifyApiError(Exception)` mit `status: int`.
- Produces `authorize_url(state: str) -> str`, `exchange_code(code: str) -> TokenSet`, `refresh(refresh_token: str) -> TokenSet`. `TokenSet(access_token, refresh_token: str | None, expires_at: datetime)`.
- Produces `class SpotifyClient(connection: SpotifyConnection, save: Callable[[SpotifyConnection], None])` mit `me() -> tuple[str, str | None]` (id, display_name), `playlists() -> list[PlaylistSummary]` (paginiert, gefiltert auf eigene/kollaborative), `playlist_tracks(playlist_id: str) -> list[SpotifyTrack]` (paginiert über `GET /v1/playlists/{id}/items`, liest `item` oder `track`, verwirft `is_local` und `type != "track"`). Erneuert den Token 60 s vor Ablauf oder nach einem 401, einmal.
- `PlaylistSummary(id: str, name: str, image: str | None, track_count: int, owner: str | None)`.

- [ ] Step 1: Tests mit gepatchtem Transport (`SpotifyClient._request` über eine injizierte `send: Callable[[urllib.request.Request], dict]`): `test_playlists_filters_foreign`, `test_playlist_tracks_paginates_and_skips_local`, `test_client_refreshes_expired_token`, `test_authorize_url_contains_scopes_and_state`.
- [ ] Step 2: FAIL. Step 3: Implementieren. Step 4: grün. Commit.

### Task 6: Erwarteter Track in der Pipeline + Importer

**Files:**
- Modify: `backend/src/api/routes/admin.py` (`process_audio_file(..., expected: SpotifyTrack | None = None)`, Prüfung in `_identify`)
- Modify: `backend/src/api/routes/youtube.py` (`YoutubeDownloadRequest` bleibt, `_download_pipeline(..., expected=None, hint=None)` reicht durch)
- Modify: `backend/src/ingest/bulk.py` (Warteschlange nimmt `BulkItem(query, expected: SpotifyTrack | None, on_done: Callable[[dict, str | None], None] | None)`; Spotify-Weg: Kandidaten über `candidate_fits`, Hint `IdentityHint(title, primary_artist, MetadataSource.SPOTIFY)`, Abbruch bei `saved`/`duplicate`, weiter bei `spotify_mismatch`)
- Modify: `backend/src/ingest/failures.py` (`spotify_mismatch`, `no_fitting_hit` in `_KNOWN_REASONS`)
- Create: `backend/src/spotify/importer.py`
- Test: `backend/tests/test_spotify_importer.py`, `backend/tests/test_expected_track_check.py`

**Interfaces:**
- `_identify`: Ist `expected` gesetzt, `metadata["metadata_source"] == "acoustid"` und `identity_matches` falsch, wird `_skipped("spotify_mismatch", metadata, None)` zurückgegeben. Das passiert **vor** dem Duplikat-Urteil.
- `PlaylistImporter(session_factory, enqueue: Callable[[list[BulkItem]], int], library: Callable[[Session], LibraryMatcher])` mit `start(user_id: int, playlist: PlaylistSummary, tracks: list[SpotifyTrack]) -> int` (Import-ID; Duplikate sofort `duplicate`, Rest `queued` + eingereiht), `record(track_row_id: int, result: dict, video_id: str | None) -> None`, `resume() -> int` (alle `queued` wieder einreihen).
- Bulk-Quelle im Tracker: `"spotify"`.

- [ ] Step 1: Tests: `test_mismatch_rejected_before_duplicate` (`precheck_skip` gepatcht, AcoustID nennt anderen Song → `spotify_mismatch`), `test_unrecognised_audio_uses_spotify_hint`, `test_start_marks_library_songs_duplicate`, `test_record_maps_results` (`saved`→saved, `duplicate`→duplicate, sonst failed + Grund), `test_resume_requeues_queued_tracks`, `test_bulk_spotify_tries_next_candidate_on_mismatch` (Service und `_download_pipeline` gefälscht).
- [ ] Step 2: FAIL. Step 3: Implementieren. Step 4: Gesamte Suite grün (bestehende Bulk-Tests unverändert). Commit.

### Task 7: Spotify-Routen, Startup, nginx

**Files:**
- Create: `backend/src/api/routes/spotify.py`, Modify: `backend/src/main.py` (Router, `PlaylistImporter.resume()` im Lifespan)
- Modify: `frontend/nginx.prod.conf` (`limit_req` für `/api/account/login|register|forgot-password`, mit `auth_request` aktiv), `frontend/nginx.conf` falls nötig, `frontend/vite.config.ts` (Proxy funktioniert für `127.0.0.1:5173`)
- Test: `backend/tests/test_spotify_routes.py`

**Interfaces:**
- `GET /api/spotify/connect` (require_user) → 302 zu `authorize_url(state)`, `state` als signiertes Cookie `mr_spotify_state` (10 min).
- `GET /api/spotify/callback?code&state` → speichert `SpotifyConnection`, 302 auf `/upload?spotify=connected`. Bei Fehler oder Ablehnung: 302 `/account?spotify=error`. Bei 403 von Spotify (Nutzer nicht im Dashboard freigeschaltet): `/account?spotify=not_allowed`.
- `DELETE /api/spotify/connection` → 204.
- `GET /api/spotify/playlists` → `list[PlaylistOut{id, name, image, track_count, owner, last_import_id: int | None}]`. 409 `"Spotify nicht verbunden"`.
- `POST /api/spotify/playlists/{playlist_id}/import` → 202 `ImportOut`.
- `GET /api/spotify/imports` → `list[ImportOut{id, name, created_at, total, saved, duplicate, failed, queued}]` (eigene, neueste zuerst, max. 20).
- `GET /api/spotify/imports/{id}` → `ImportDetailOut{...ImportOut, tracks: list[ImportTrackOut{position, title, artists: list[str], status, reason, song_id}]}`.

- [ ] Step 1: Tests (Client und Importer per Dependency-Override gefälscht): `test_connect_requires_login`, `test_callback_rejects_bad_state`, `test_callback_stores_connection`, `test_import_returns_counts`, `test_imports_only_own`.
- [ ] Step 2: FAIL. Step 3: Implementieren. Step 4: grün. Commit.

### Task 8: Frontend (webbuilder + impeccable)

**Files:**
- Modify: `frontend/src/services/api.ts` (Account- und Spotify-Aufrufe, Typen als Interfaces)
- Create: `frontend/src/account/useAccount.ts` (Store wie `router.tsx` mit `useSyncExternalStore`), `frontend/src/components/account/AccountMenu.tsx`, `AccountPage.tsx`, `ResetPasswordPage.tsx`, `frontend/src/components/upload/SpotifyImport.tsx`
- Modify: `frontend/src/App.tsx` (Routen `/account`, `/reset-password/:token`, Menü rechts im Header neben dem Song-Zähler), `UploadPage.tsx` (Abschnitt einbinden), `PipelineList.tsx` (Quelle `spotify`)

**Interfaces:** Consumes die Routen aus Task 3 und 7 exakt.

- [ ] Step 1: Agent `webbuilder` mit Skill `impeccable` beauftragen: Spec, diese Task und die API-Verträge mitgeben. Bestehenden Stil übernehmen, Mobil-Layout prüfen.
- [ ] Step 2: `docker exec music_recommender_v2-frontend-1 npx tsc --noEmit` ohne Fehler.
- [ ] Step 3: Playwright gegen `http://127.0.0.1:5173`: registrieren, abmelden, anmelden, Passwort vergessen (Link aus dem Backend-Log), Upload-Seite ohne und mit Login. Screenshots Desktop + 390 px.
- [ ] Step 4: Commit.

### Task 9: End-to-end-Nachweis mit echter Playlist

- [ ] Step 1: Benni verbindet lokal Spotify (`http://127.0.0.1:5173/account`) und importiert eine kleine eigene Playlist (10–20 Songs).
- [ ] Step 2: Skript im Scratchpad vergleicht jeden `saved`-Track: `songs.title/artist` gegen Spotify-Titel/-Künstler mit `identity_matches`, und `songs.youtube_video_id` ist gesetzt. Erwartet: 0 Abweichungen. Abweichungen → systematic-debugging.
- [ ] Step 3: `failed`-Tracks mit Grund auflisten und stichprobenartig prüfen, ob die Ablehnung berechtigt war.
- [ ] Step 4: README/.env.example ergänzen (neue Variablen, Spotify-Dashboard-Schritte). Commit.
