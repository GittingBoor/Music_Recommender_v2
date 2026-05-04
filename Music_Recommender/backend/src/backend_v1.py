import uvicorn
from pymongo import MongoClient
from pydantic import parse_obj_as
from typing import List
import numpy as np
from bson.objectid import ObjectId
from collections import defaultdict
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from src.data_types import *
from src.nearest_neighbour import *
import time

app = FastAPI()
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# mongoDB atlas
client = MongoClient('mongodb://host.docker.internal:27017')
#client = MongoClient("localhost:27017")
db = client['musemantiq']
collection = db['files']

# client = MongoClient('mongodb://host.docker.internal:27017')
# db = client['MusemantIQ']
# collection = db['Audio_Files']

collection.create_index([('title','text')])

playlist_length = 16
ip_music_server = 'http://127.0.0.1:8080/Audio/'
ip_album_art_server = 'http://127.0.0.1:8080/Album_Art/'

def normalize_data(data):
    return (data - np.min(data)) / (np.max(data) - np.min(data))

def get_song_id():
    song_ID = []
    for document in collection.find():
        song_ID.append(document["_id"])
    return song_ID

def get_song_id_and_dimensions(playlistType, genre):
    song_ID = []
    song_Dimensions = []

    if(playlistType == 'emotional'):
        features = {'features.valence': 1, 'features.arousal': 1, 'features.authenticity': 1,
                    'features.timeliness': 1, 'features.complexity': 1}

    if (playlistType == 'essentia'):
        features = {'features.bpm': 1, 'features.voice': 1, 'features.female': 1,
                    'features.danceability': 1, 'features.tonal': 1}

    if (playlistType == 'allFeatures'):
        features = {'features.valence': 1, 'features.arousal': 1, 'features.authenticity': 1,
                    'features.timeliness': 1, 'features.complexity': 1, 'features.voice': 1,
                    'features.danceability': 1, 'features.tonal': 1}

    
    if(genre == 'none'):
        for doc in collection.find({}, features):
            song_ID.append(doc["_id"])
            song_Dimensions.append(list(doc["features"].values()))
    else:
        # find all documents that contain the genre in the top 3 genres
        query = 'features.genres.top3_genres.' + str(genre)
        for doc in collection.find({query: {'$exists': True}}, features):
            
            song_ID.append(doc["_id"])
            song_Dimensions.append(list(doc["features"].values()))
    return [song_ID, song_Dimensions]

def sort_genres_according_to_correlation(song):
    """
    sort the genre index from db according to correlation of Genre Rock (see data_types.py)
    genres[10] gets deleted, no one needs indie pop, genre chill gets send to web app, but it
    is least correlated and does not get displayed in bubble chart
    """
    genres = [0] * 33

    for index, feature in enumerate(song['features']['genres']['all_genres']):
        val = song['features']['genres']['all_genres'][feature]
        genres[genreCorr.index(genreDataBase[index])] = val

    # normalize color of genres
    genres = list(normalize_data(np.array(genres)))
    del genres[10] # delete genre indie pop, genre chill is least correlated and also not in web app
    song['features']['genres']['all_genres'] = genres
    
    return song

def find_duplicate_songs_in_playlist(artist, playlist):
    l = []
    playlist_new = playlist.copy()

    tally = defaultdict(list)
    for i,item in enumerate(artist):
        tally[item].append(i)

    for dup in sorted(((key,locs) for key,locs in tally.items() if len(locs)>1)):
        l.append(dup[1][1:])

    l = [item for sublist in l for item in sublist]

    for index in sorted(l, reverse=True):
        del playlist_new[index]

    while len(playlist_new) < playlist_length:
        playlist_new = playlist.copy()
        l.remove(min(l))
        for index in sorted(l, reverse=True):
            del playlist_new[index]

    while len(playlist_new) > playlist_length:
            playlist_new = playlist_new[:-1]

    return playlist_new

def get_song_information(top_ID):
    playlist = []

    for i, val in enumerate(top_ID):
        for song in collection.find({"_id":ObjectId(str(val))}):
            entries_to_remove = ['_id']
            for i in entries_to_remove:
                song.pop(i, None)
            song = sort_genres_according_to_correlation(song)
            song['ids']['track_id'] = ip_music_server + song['ids']['track_id']
            song['ids']['artwork_id'] = ip_album_art_server + song['ids']['artwork_id']

            playlist.append(song)

    return parse_obj_as(List[Song], playlist)

def generatePlaylist(inputVector, playlistType, genre):
    song_id_dimensions = get_song_id_and_dimensions(playlistType, genre)
    start = time.time()
    #top_songs_ids = k_d_tree(song_id_dimensions, inputVector, playlist_length)

    top_songs_ids = k_d_tree(song_id_dimensions, inputVector, playlist_length)
    end = time.time()
    print(end - start)
    playlist = get_song_information(top_songs_ids)
    return playlist

def generateRandomPlaylist():
    random_playlist = []
    random_songs = collection.aggregate([{'$sample': {"size": playlist_length}}])

    for song in random_songs:     
        song = sort_genres_according_to_correlation(song)
        song['ids']['track_id'] = ip_music_server + song['ids']['track_id']
        song['ids']['artwork_id'] = ip_album_art_server + song['ids']['artwork_id']
        random_playlist.append(song)

    return random_playlist

def searchSongs(text):
    searchResults = []
    cursor = collection.find({"$text": {"$search": str(text)}}, {'score': {'$meta': "textScore"}})
    cursor = cursor.sort([('score', {'$meta': 'textScore'})])

    for song in cursor:
        song = sort_genres_according_to_correlation(song)
        song['ids']['track_id'] = ip_music_server + song['ids']['track_id']
        song['ids']['artwork_id'] = ip_album_art_server + song['ids']['artwork_id']
        searchResults.append(song)

    return searchResults

@app.get("/")
def home():
    return {"message": "Home"}

@app.get("/generateRandomPlaylist", response_model=List[Song])
def generateRandom():
    playlist = generateRandomPlaylist()
    return playlist

@app.post("/generateEmotionalPlaylist", response_model=List[Song])
def generate(features: EmotionFeatures):
    inputVector = [features.valence, features.arousal, features.authenticity, features.timeliness, features.complexity]
    playlist = generatePlaylist(inputVector, 'emotional', features.genre)
    return playlist

@app.post("/generateEssentiaPlaylist", response_model=List[Song])
def generate(features: EssentiaFeatures):
    inputVector = [features.bpm, features.voice, features.female, features.danceable, features.tonal]
    playlist = generatePlaylist(inputVector, 'essentia', features.genre)
    return playlist

@app.post("/generateAllFeaturesPlaylist", response_model=List[Song])
def generate(features: AllFeatures):
    inputVector = [features.valence, features.arousal, features.authenticity, features.timeliness, features.complexity,
                   features.voice, features.danceable, features.tonal]
    playlist = generatePlaylist(inputVector, 'allFeatures', features.genre)
    return playlist

@app.post("/search", response_model=List[Song])
def generate(text: Search):
    songs = searchSongs(text)
    return songs

if __name__ == "__main__":
    uvicorn.run("src.backend_v1:app", host="0.0.0.0", port=8000, reload=True)
