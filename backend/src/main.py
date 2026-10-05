from contextlib import asynccontextmanager

import essentia
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import check_required_keys
from src.api.routes.admin import router as admin_router
from src.api.routes.analysis import router as analysis_router
from src.api.routes.audio import router as audio_router
from src.api.routes.auth import router as auth_router
from src.api.routes.ingest import router as ingest_router
from src.api.routes.songs import router as songs_router
from src.api.routes.umap import router as umap_router, warm_umap
from src.api.routes.upload import router as upload_router
from src.api.routes.youtube import router as youtube_router, warm_example_pool

@asynccontextmanager
async def _lifespan(app: FastAPI):
    check_required_keys()
    # Essentia writes "No network created, or last created network has been
    # deleted..." for every analysed frame, >100k lines per few songs; the CLI
    # pipeline silences it the same way.
    essentia.log.infoActive = False
    essentia.log.warningActive = False
    warm_example_pool()
    warm_umap()
    yield


app = FastAPI(title="Music Recommender API", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(songs_router, prefix="/api")
app.include_router(umap_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(audio_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(youtube_router, prefix="/api")
app.include_router(ingest_router, prefix="/api")
app.include_router(auth_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
