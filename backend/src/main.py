from fastapi import FastAPI

app = FastAPI(title="Music Recommender API")


@app.get("/health")
def health():
    return {"status": "ok"}
