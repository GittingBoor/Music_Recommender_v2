from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import check_required_keys
from src.api.routes.admin import router as admin_router
from src.api.routes.analysis import router as analysis_router
from src.api.routes.audio import router as audio_router
from src.api.routes.songs import router as songs_router
from src.api.routes.umap import router as umap_router
from src.api.routes.upload import router as upload_router
from src.api.routes.youtube import router as youtube_router

@asynccontextmanager
async def _lifespan(app: FastAPI):
    check_required_keys()
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


@app.get("/health")
def health():
    return {"status": "ok"}
