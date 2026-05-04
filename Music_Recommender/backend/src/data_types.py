from pydantic import BaseModel

class Search(BaseModel):
    searchSong: str

class Song(BaseModel):
    title: str
    album: str
    artist: str
    duration_s: int
    features: dict
    features_frames: dict
    songStructure: dict
    ids: dict

class AllFeatures(BaseModel):
    valence: float
    arousal: float
    authenticity: float
    timeliness: float
    complexity: float
    danceable: float
    tonal: float
    voice: float
    genre: str

class EmotionFeatures(BaseModel):
    valence: float
    arousal: float
    authenticity: float
    timeliness: float
    complexity: float
    genre: str


class EssentiaFeatures(BaseModel):
    danceable: float
    tonal: float
    voice: float
    female: float
    bpm: float
    genre: str


genreDataBase = ['rock', 'pop', 'alternative', 'indie', 'electronic', 'dance',
       'alternative rock', 'jazz', 'metal', 'chillout', 'classic rock', 'soul',
       'indie rock', 'electronica', 'folk', 'chill', 'instrumental', 'punk',
       'blues', 'hard rock', 'ambient', 'acoustic', 'experimental', 'Hip-Hop',
       'country', 'easy listening', 'funk', 'electro', 'heavy metal',
       'Progressive rock', 'rnb', 'indie pop', 'House']

genreCorr = ['rock', 'alternative rock', 'alternative', 'hard rock', 'indie rock', 'classic rock', 'punk',
                'Progressive rock', 'indie', 'heavy metal', 'indie pop', 'metal', 'blues', 'country', 'acoustic',
                'folk', 'pop', 'funk', 'experimental', 'instrumental', 'soul', 'Hip-Hop', 'easy listening', 'House',
                'rnb', 'electro', 'dance', 'ambient', 'jazz', 'chillout', 'electronic', 'electronica', 'chill']

