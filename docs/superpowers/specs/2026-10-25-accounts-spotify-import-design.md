# Accounts, Spotify-Verbindung und Playlist-Import – Design

Stand: 2026-10-25 · abgestimmt mit Benni im Chat

## Warum

Benni will, dass Nutzer ihren Spotify-Account verbinden und ganze Playlists mit einem Klick in die
gemeinsame Song-Datenbank holen können. Accounts sind die Grundlage dafür und für spätere Funktionen.
Es dürfen **keine falschen Songs** in die Datenbank kommen.

## Rahmen (von Benni festgelegt)

- Die gemeinsame Vorab-Passwortseite (`/login`, nginx `auth_request`) bleibt unverändert davor.
- Ohne Account funktioniert alles wie bisher, auch der Upload. Ein Account ist nur für Spotify nötig.
- Jeder darf sich selbst registrieren (E-Mail + Passwort). Login oben rechts im Header.
- Passwort zurücksetzen per E-Mail an jede Adresse. Versand über **Brevo** (Transactional-API).
- Jeder Nutzer verbindet seinen eigenen Spotify-Account. Die Spotify-App (Development Mode, nach
  Feb. 2026 angelegt) erlaubt **5 Nutzer**, die Benni im Spotify-Dashboard freischaltet. Benni hat Premium.
- Importierbar sind nur Playlists, die der Nutzer **besitzt oder bei denen er mitarbeitet**. Spotify liefert
  für fremde Playlists keine Songs mehr. Kein Workaround über die Embed-Seite.
- Lieblingssongs („Gefällt mir“) vorerst nicht.
- Alle Songs gehen in die gemeinsame Datenbank. Songs, die schon da sind, werden übersprungen.
- Songs ohne sicheren YouTube-Treffer werden nicht übernommen und mit Grund angezeigt.
- Redirect-URIs (bei Spotify eingetragen):
  `https://music.gittingboor.de/api/spotify/callback`, `http://127.0.0.1:5173/api/spotify/callback`.

## Nicht-Ziele

- Keine Pflicht zum Login, keine Rechte/Rollen, keine Songs pro Nutzer.
- Kein Import fremder Playlists, keine Lieblingssongs, kein Zurückschreiben nach Spotify.
- Anti-Ziel: Ein Import, der „funktioniert“, aber falsche Aufnahmen (Cover, Live, anderer Song) speichert.

## Backend

**Neue Tabellen** (Alembic-Migration nach `a2b3c4d5e6f7`):

- `users`: id, email (unique, kleingeschrieben), password_hash (scrypt wie die Site), created_at.
- `password_reset_tokens`: sha256 des Tokens, user_id, expires_at (1 h), used_at.
- `spotify_connections`: user_id (PK), spotify_user_id, display_name, access_token, refresh_token,
  expires_at.
- `playlist_imports`: id, user_id, spotify_playlist_id, name, created_at.
- `playlist_import_tracks`: id, import_id, position, spotify_track_id, title, artists, duration_ms, isrc,
  status (`queued` | `saved` | `duplicate` | `failed`), reason, song_id, video_id.

**Nutzer-Session:** eigenes Cookie `mr_user`, signiert (`<user_id>.<expiry>.<hmac>`). Der HMAC-Schlüssel
hängt am Passwort-Hash des Nutzers, also meldet ein Reset alle alten Sitzungen ab.

**Routen** unter `/api/account/*`: `register`, `login`, `logout`, `me`, `forgot-password`
(antwortet immer 204, verrät nicht, ob die Adresse existiert), `reset-password`.
Der Reset-Link ist `https://music.gittingboor.de/reset-password/<token>`, mit dem Token im **Pfad**, weil
nginx bei der Vorab-Passwortseite nur `$uri` als `next` weitergibt.
Fehlt die Brevo-Konfiguration, loggt das Backend den Link als Warnung (lokale Entwicklung).

**Spotify** unter `/api/spotify/*`: `connect` (Redirect zu Spotify, `state` im signierten Cookie),
`callback`, `DELETE connection`, `playlists` (nur eigene/kollaborative), `POST playlists/{id}/import`,
`imports` (Liste mit Zählern), `imports/{id}` (alle Tracks mit Status). Scopes:
`playlist-read-private playlist-read-collaborative`. Tokens werden mit dem Refresh-Token erneuert.
HTTP wie im übrigen Code über `urllib` (keine neue Abhängigkeit).

**Import-Ablauf:**

1. Alle Tracks der Playlist holen (paginiert, `/items`), lokale Dateien und Podcasts verwerfen.
2. Schon vorhandene Songs (Song-ID aus Titel + Hauptkünstler oder `LibraryMatcher`) → `duplicate`.
3. Der Rest kommt in die bestehende Bulk-Warteschlange (`src/ingest/bulk.py`) als Job mit
   *erwartetem Track*. Er ist in der Pipeline-Ansicht sichtbar, `source = "spotify"`.
4. Kandidatenwahl: Suche „Künstler – Titel“ und das bestehende Ranking, dazu ein Vorfilter.
   Der Titel muss passen. Die Länge muss passen: ±15 s oder bis zu +25 % bei Videos mit Intro/Outro.
   Live/Cover/Remix/… wird verworfen, außer der Spotify-Titel trägt den Zusatz selbst. Höchstens 3 Versuche.
5. **Absicherung nach dem Download:** `process_audio_file` bekommt den erwarteten Track. Erkennt AcoustID
   einen anderen Song (Titel/Künstler normalisiert verglichen, Klammerzusätze, „feat.“, „Remastered“ und
   Akzente ignoriert), wird **nicht gespeichert** (`spotify_mismatch`) und der nächste Kandidat probiert.
   Kennt AcoustID die Aufnahme nicht, gilt der Spotify-Titel/-Künstler als Metadaten. Das ist nur erlaubt,
   weil der Kandidat den strengen Vorfilter (Titel + Künstler + Länge) bestanden hat.
6. Ergebnis pro Track in `playlist_import_tracks`, Fehlschläge zusätzlich in `ingest_failures`.
7. Nach einem Backend-Neustart werden Tracks mit Status `queued` automatisch wieder eingereiht.

## Frontend

- Header rechts: „Anmelden“ bzw. die E-Mail des Nutzers. Neue Seite `/account`: Login/Registrierung,
  Passwort vergessen, Spotify verbinden/trennen, Abmelden. Neue Seite `/reset-password/:token`.
- Upload-Seite, neuer Abschnitt „Spotify-Playlists“: ohne Login ein Hinweis mit Link zum Anmelden,
  ohne Spotify-Verbindung der Knopf „Spotify verbinden“, mit Verbindung die Liste der Playlists mit
  „Importieren“. Laufende und fertige Importe zeigen Zähler (übernommen / schon vorhanden / nicht übernommen /
  in Arbeit) und aufklappbar die nicht übernommenen Songs mit Grund.
- UI-Arbeit läuft über den Agent `webbuilder` mit dem Skill `impeccable` und passt sich an den
  bestehenden Stil an (Tailwind-Tokens `ink`, `line`, `ground`, Klassen `tab`, `btn-quiet`).

## Tests / Nachweis

- Pytest: Passwort/Session/Reset-Token, Account-Routen (Fake-DB wie `test_auth.py`), Vorfilter und
  Abgleich mit kniffligen Fällen (Remastered, feat., Live, Cover, andere Länge, Akzente, Mehrfachkünstler).
- End-to-end auf dem lokalen Stack mit einer echten Playlist von Benni: Stichprobe aller übernommenen Songs
  gegen Spotify (Titel/Künstler) per Skript, Ergebnis im Protokoll.

## Was Benni bereitstellen muss

- `SPOTIFY_CLIENT_SECRET` der App (falls die Client-ID nicht schon die in `.env` ist).
- Brevo-Account: API-Key und eine verifizierte Absenderadresse (`BREVO_API_KEY`, `MAIL_FROM`).
- Spotify-Dashboard → User Management: die Spotify-E-Mails der bis zu 5 Nutzer.
