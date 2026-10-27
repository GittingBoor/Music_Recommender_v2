"""Connect a personal account to Spotify and import its playlists into the library.

The browser goes /api/spotify/connect → Spotify's consent page → /api/spotify/callback,
which stores the tokens and sends it back to the page it came from.

/api/spotify/library is the personal view: which library songs are in each of
the user's playlists and saved tracks (a sync compares them with Spotify again).
"""
import hmac
import logging
import secrets
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.user import current_user, require_user
from src.core.config import settings
from src.db.models import PlaylistImport, PlaylistImportTrack, SpotifyConnection, User
from src.db.session import get_session
from src.ingest import bulk
from src.spotify import importer as importer_module
from src.spotify import library
from src.spotify.client import PlaylistSummary, SpotifyApiError, SpotifyClient, TokenSet, authorize_url, exchange_code
from src.spotify.importer import PlaylistImporter

logger = logging.getLogger(__name__)
router = APIRouter()

STATE_COOKIE = "mr_spotify_state"
_STATE_MAX_AGE = 10 * 60
_STATE_COOKIE_PATH = "/api/spotify"
# Pages the callback may send the browser back to.
_RETURN_PAGES = ("/upload", "/account")
_IMPORT_LIST_LIMIT = 20

_importer = PlaylistImporter(get_session, bulk.enqueue_items)

ClientFactory = Callable[[SpotifyConnection, Session], SpotifyClient]


def get_importer() -> PlaylistImporter:
    return _importer


def resume_playlist_imports() -> None:
    """Queue tracks an earlier process left unfinished (called at startup).

    A failure (e.g. migrations not run yet) is logged and the app starts anyway.
    """
    try:
        _importer.resume()
    except Exception:
        logger.exception("[Spotify] Could not resume playlist imports; run `alembic upgrade head`")


def get_client_factory() -> ClientFactory:
    def make(connection: SpotifyConnection, db: Session) -> SpotifyClient:
        def save(updated: SpotifyConnection) -> None:
            db.add(updated)
            db.commit()
        return SpotifyClient(connection, save)
    return make


def get_code_exchange() -> Callable[[str], TokenSet]:
    return exchange_code


class PlaylistOut(BaseModel):
    id: str
    name: str
    image: str | None
    track_count: int
    owner: str | None
    last_import_id: int | None


class ImportOut(BaseModel):
    id: int
    playlist_id: str
    name: str
    created_at: datetime
    total: int
    saved: int
    duplicate: int
    failed: int
    queued: int
    # When the last track left the queue; null while tracks are still queued.
    finished_at: datetime | None
    # Some tracks predate finished_at, so the real end may be later.
    finished_estimated: bool


class ImportTrackOut(BaseModel):
    position: int
    title: str
    artists: list[str]
    status: str
    reason: str | None
    song_id: str | None


class ImportDetailOut(ImportOut):
    tracks: list[ImportTrackOut]


class LibraryPlaylistOut(BaseModel):
    id: int
    spotify_playlist_id: str
    # "playlist" or "liked" (the saved tracks)
    kind: str
    name: str
    image: str | None
    # Distinct tracks on Spotify; song_ids are the ones in the library, in playlist order.
    track_count: int
    synced_at: datetime
    song_ids: list[str]


class LibrarySyncOut(BaseModel):
    playlists: list[LibraryPlaylistOut]
    # The connection predates the saved-tracks permission; reconnecting grants it.
    liked_needs_reconnect: bool


def _require_configured() -> None:
    if not (settings.spotify_client_id and settings.spotify_redirect_uri):
        raise HTTPException(status_code=503, detail="Spotify is not configured: set SPOTIFY_CLIENT_ID and SPOTIFY_REDIRECT_URI.")


def _redirect(to: str) -> RedirectResponse:
    response = RedirectResponse(to, status_code=302)
    response.delete_cookie(STATE_COOKIE, path=_STATE_COOKIE_PATH)
    return response


@router.get("/spotify/connect")
def connect(next: str = Query("/account"), user: User | None = Depends(current_user)) -> Response:
    """Send the browser to Spotify's consent page."""
    _require_configured()
    if user is None:
        return RedirectResponse("/account?spotify=login", status_code=302)
    state = secrets.token_urlsafe(24)
    back = next if next in _RETURN_PAGES else "/account"
    response = RedirectResponse(authorize_url(state), status_code=302)
    response.set_cookie(
        STATE_COOKIE, f"{state}|{back}", max_age=_STATE_MAX_AGE, path=_STATE_COOKIE_PATH,
        httponly=True, secure=settings.session_cookie_secure, samesite="lax",
    )
    return response


@router.get("/spotify/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    user: User | None = Depends(current_user),
    db: Session = Depends(get_db),
    client_factory: ClientFactory = Depends(get_client_factory),
    exchange: Callable[[str], TokenSet] = Depends(get_code_exchange),
) -> Response:
    """Spotify sends the browser here after the consent page."""
    if user is None:
        return _redirect("/account?spotify=login")
    if error:
        logger.info("[Spotify] User %d declined: %s", user.id, error)
        return _redirect("/account?spotify=denied")
    expected_state, _, back = request.cookies.get(STATE_COOKIE, "").partition("|")
    if not code or not state or not expected_state or not hmac.compare_digest(state, expected_state):
        logger.warning("[Spotify] Callback for user %d with missing or wrong state", user.id)
        return _redirect("/account?spotify=error")
    try:
        _store_connection(user, exchange(code), db, client_factory)
    except SpotifyApiError as exc:
        logger.warning("[Spotify] Connecting user %d failed: %s", user.id, exc)
        # Development-mode apps answer 403 for accounts not added under "User Management".
        return _redirect("/account?spotify=not_allowed" if exc.status == 403 else "/account?spotify=error")
    return _redirect(f"{back if back in _RETURN_PAGES else '/account'}?spotify=connected")


def _store_connection(user: User, tokens: TokenSet, db: Session, client_factory: ClientFactory) -> None:
    if not tokens.refresh_token:
        raise SpotifyApiError(0, "token response without refresh_token")
    connection = db.get(SpotifyConnection, user.id) or SpotifyConnection(user_id=user.id, spotify_user_id="")
    connection.access_token = tokens.access_token
    connection.refresh_token = tokens.refresh_token
    connection.expires_at = tokens.expires_at
    spotify_id, display_name = client_factory(connection, db).me()
    connection.spotify_user_id = spotify_id
    connection.display_name = display_name
    db.add(connection)
    db.commit()
    logger.info("[Spotify] User %d connected Spotify account %s", user.id, spotify_id)


@router.delete("/spotify/connection", status_code=204)
def disconnect(user: User = Depends(require_user), db: Session = Depends(get_db)) -> Response:
    connection = db.get(SpotifyConnection, user.id)
    if connection is not None:
        db.delete(connection)
        db.commit()
    return Response(status_code=204)


def _client(user: User, db: Session, client_factory: ClientFactory) -> SpotifyClient:
    connection = db.get(SpotifyConnection, user.id)
    if connection is None:
        raise HTTPException(status_code=409, detail="Spotify ist nicht verbunden.")
    return client_factory(connection, db)


def _spotify_http_error(exc: SpotifyApiError) -> HTTPException:
    logger.warning("[Spotify] API call failed: %s", exc)
    if exc.status in (400, 401):
        # The refresh token was revoked (app removed in the Spotify account settings).
        return HTTPException(status_code=409, detail="Die Spotify-Verbindung ist abgelaufen. Bitte neu verbinden.")
    if exc.status == 403:
        return HTTPException(status_code=403, detail="Dieser Spotify-Account ist für die App nicht freigeschaltet.")
    # 503, not 502: Cloudflare swaps origin 502/504 for its own page and the detail is lost.
    return HTTPException(status_code=503, detail="Spotify antwortet gerade nicht. Bitte später erneut versuchen.")


@router.get("/spotify/playlists", response_model=list[PlaylistOut])
def playlists(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    client_factory: ClientFactory = Depends(get_client_factory),
) -> list[PlaylistOut]:
    """The user's own and collaborative playlists, with their latest import if any."""
    client = _client(user, db, client_factory)
    try:
        found = client.playlists()
    except SpotifyApiError as exc:
        raise _spotify_http_error(exc) from exc
    last = dict(
        db.query(PlaylistImport.spotify_playlist_id, func.max(PlaylistImport.id))
        .filter(PlaylistImport.user_id == user.id)
        .group_by(PlaylistImport.spotify_playlist_id)
        .all()
    )
    return [PlaylistOut(**vars(p), last_import_id=last.get(p.id)) for p in found]


@router.post("/spotify/playlists/{playlist_id}/import", response_model=ImportOut, status_code=202)
def import_playlist(
    playlist_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    client_factory: ClientFactory = Depends(get_client_factory),
    importer: PlaylistImporter = Depends(get_importer),
) -> ImportOut:
    """Queue every song of the playlist that is not in the library yet."""
    _require_acoustid()
    if _import_running(user.id, playlist_id, db):
        raise HTTPException(status_code=409, detail="Diese Playlist wird gerade schon importiert.")
    client = _client(user, db, client_factory)
    try:
        playlist = _find_playlist(client.playlists(), playlist_id)
        tracks = client.playlist_tracks(playlist.id)
    except SpotifyApiError as exc:
        raise _spotify_http_error(exc) from exc
    import_id = importer.start(user.id, playlist, tracks)
    db.expire_all()
    return _import_out(db.get(PlaylistImport, import_id), db)


@router.post("/spotify/imports/{import_id}/retry", response_model=ImportOut, status_code=202)
def retry_failed(
    import_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    importer: PlaylistImporter = Depends(get_importer),
) -> ImportOut:
    """Search, download and check the import's failed tracks once more."""
    _require_acoustid()
    entry = _own_import(import_id, user, db)
    if not importer.retry_failed(entry.id):
        raise HTTPException(status_code=409, detail="Dieser Import hat keine fehlgeschlagenen Songs.")
    db.expire_all()
    return _import_out(entry, db)


def _require_acoustid() -> None:
    if not settings.acoustid_api_key:
        # Without fingerprints nothing could tell a wrong YouTube upload from the right song.
        raise HTTPException(status_code=503, detail="Playlist import needs ACOUSTID_API_KEY to verify songs.")


def _own_import(import_id: int, user: User, db: Session) -> PlaylistImport:
    entry = db.get(PlaylistImport, import_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status_code=404, detail="Import nicht gefunden.")
    return entry


def _import_running(user_id: int, playlist_id: str, db: Session) -> bool:
    """True while an earlier import of this playlist still has queued tracks."""
    return db.query(PlaylistImportTrack.id).join(
        PlaylistImport, PlaylistImport.id == PlaylistImportTrack.import_id,
    ).filter(
        PlaylistImport.user_id == user_id,
        PlaylistImport.spotify_playlist_id == playlist_id,
        PlaylistImportTrack.status == importer_module.QUEUED,
    ).first() is not None


def _find_playlist(found: list[PlaylistSummary], playlist_id: str) -> PlaylistSummary:
    playlist = next((p for p in found if p.id == playlist_id), None)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist nicht gefunden (nur eigene und gemeinsame Playlists).")
    return playlist


def _counts(import_id: int, db: Session) -> dict[str, int]:
    rows = (
        db.query(PlaylistImportTrack.status, func.count())
        .filter(PlaylistImportTrack.import_id == import_id)
        .group_by(PlaylistImportTrack.status)
        .all()
    )
    return {status: count for status, count in rows}


def _end(import_id: int, db: Session) -> tuple[datetime | None, bool]:
    """``(latest finished_at, whether a finished track has none)`` of the import's tracks."""
    latest, untimed = (
        db.query(
            func.max(PlaylistImportTrack.finished_at),
            func.count(PlaylistImportTrack.id).filter(PlaylistImportTrack.finished_at.is_(None)),
        )
        .filter(PlaylistImportTrack.import_id == import_id, PlaylistImportTrack.status != importer_module.QUEUED)
        .one()
    )
    return latest, untimed > 0


def _import_out(entry: PlaylistImport, db: Session) -> ImportOut:
    counts = _counts(entry.id, db)
    queued = counts.get(importer_module.QUEUED, 0)
    latest, estimated = _end(entry.id, db)
    finished_at = None if queued else (latest or entry.created_at)
    return ImportOut(
        id=entry.id, playlist_id=entry.spotify_playlist_id, name=entry.name, created_at=entry.created_at,
        total=sum(counts.values()),
        saved=counts.get(importer_module.SAVED, 0),
        duplicate=counts.get(importer_module.DUPLICATE, 0),
        failed=counts.get(importer_module.FAILED, 0),
        queued=queued,
        finished_at=finished_at,
        finished_estimated=finished_at is not None and estimated,
    )


@router.get("/spotify/imports", response_model=list[ImportOut])
def imports(user: User = Depends(require_user), db: Session = Depends(get_db)) -> list[ImportOut]:
    """The user's latest playlist imports, newest first."""
    entries = (
        db.query(PlaylistImport).filter(PlaylistImport.user_id == user.id)
        .order_by(PlaylistImport.id.desc()).limit(_IMPORT_LIST_LIMIT).all()
    )
    return [_import_out(e, db) for e in entries]


@router.get("/spotify/imports/{import_id}", response_model=ImportDetailOut)
def import_detail(import_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)) -> ImportDetailOut:
    entry = _own_import(import_id, user, db)
    rows = (
        db.query(PlaylistImportTrack).filter(PlaylistImportTrack.import_id == import_id)
        .order_by(PlaylistImportTrack.position).all()
    )
    tracks = [
        ImportTrackOut(
            position=r.position, title=r.title, artists=importer_module.artists_of(r),
            status=r.status, reason=r.reason, song_id=r.song_id,
        )
        for r in rows
    ]
    return ImportDetailOut(**_import_out(entry, db).model_dump(), tracks=tracks)


def _library_out(db: Session, user_id: int) -> list[LibraryPlaylistOut]:
    return [
        LibraryPlaylistOut(
            id=e.id, spotify_playlist_id=e.spotify_playlist_id, kind=e.kind, name=e.name, image=e.image,
            track_count=e.track_count, synced_at=e.synced_at, song_ids=song_ids,
        )
        for e, song_ids in library.user_playlists(db, user_id)
    ]


@router.get("/spotify/library", response_model=list[LibraryPlaylistOut])
def library_playlists(user: User | None = Depends(current_user), db: Session = Depends(get_db)) -> list[LibraryPlaylistOut]:
    """The user's playlists as last synced or imported; empty when logged out."""
    return [] if user is None else _library_out(db, user.id)


@router.post("/spotify/library/sync", response_model=LibrarySyncOut)
def sync_library(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    client_factory: ClientFactory = Depends(get_client_factory),
) -> LibrarySyncOut:
    """Read every playlist and the saved tracks from Spotify again and match them with the library."""
    client = _client(user, db, client_factory)
    try:
        fetched = [(p, client.playlist_tracks(p.id)) for p in client.playlists()]
    except SpotifyApiError as exc:
        raise _spotify_http_error(exc) from exc
    liked = None
    try:
        liked = client.liked_tracks()
    except SpotifyApiError as exc:
        # The playlists just worked, so a 403 here is the missing user-library-read scope.
        if exc.status != 403:
            raise _spotify_http_error(exc) from exc
        logger.info("[Spotify] User %d: saved tracks need a reconnect (scope)", user.id)
    for playlist, tracks in fetched:
        library.store_playlist(db, user.id, playlist.id, playlist.name, playlist.image, tracks)
    if liked is not None:
        library.store_liked(db, user.id, liked)
    library.remove_missing(db, user.id, {p.id for p, _ in fetched})
    db.commit()
    logger.info("[Spotify] User %d synced %d playlists", user.id, len(fetched))
    return LibrarySyncOut(playlists=_library_out(db, user.id), liked_needs_reconnect=liked is None)
