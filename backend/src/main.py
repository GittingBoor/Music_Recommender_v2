from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.songs import router as songs_router

app = FastAPI(title="Music Recommender API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(songs_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
