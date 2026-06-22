import pathlib
import os
import json
from essentia.standard import MonoLoader
from audio_feature_extraction import AudioFeatureExtraction
from config_audio import working_dir
import sys

sys.path.append(working_dir + '/src')  
from createPDF import CreatePDF
from db_connector import store_to_mongoDB

class AudioProcess(AudioFeatureExtraction):
    
    def __init__(self, file_path):
        self.file_path = file_path
        self.filename = file_path.split('/')[-1]
        self.audio = MonoLoader(filename=self.file_path, sampleRate=self.sr)()

    def store_to_json(self, json_path=pathlib.Path().absolute(), features=None, metadata=None):
        
        if metadata == None:
            filename = self.filename.split('.')[0]
        else:
            filename = '_'.join([self.filename.split('.')[0], metadata['album'], metadata['artist']])

        if '_id' in features:
            del features['_id']

        with open(os.path.join(json_path, filename + '.json'), 'w') as outfile:
            json.dump(features, outfile, indent=4, ensure_ascii=False)

    def store_to_pdf(self, pdf_path=pathlib.Path().absolute(), features=None):
        """stores only AIM Features to PDF"""
        CreatePDF(features=features, pdf_path=pdf_path).createPDF__aim_features()

    def store_to_db(self, features):
        """stores AIM Features and Metadata to DB, copies and renames audio according to track_id"""
        ids = store_to_mongoDB(features, self.file_path)
        return ids
        
    def compute_aim_features(self, metadata=None, ml_model='rf'):
        aim_features = self.extract_aim_features(gmbi_model=ml_model)  
        
        if metadata == None:
            aim_features = {**{'song_title': self.filename.split('.')[0], 'duration_s': self.get_duration()}, **aim_features}
        else:
            aim_meta_data = {'title': self.filename.split('.')[0], 'album': metadata['album'], 'artist': metadata['artist'], 
                             'duration_s': self.get_duration()}
            aim_features = {**aim_meta_data, **aim_features}
        
        return aim_features

    def compute_all_features(self, statistics=True, frames=True):
        all_features = self.extract_all_features(statistics=statistics, frames=frames)
        return all_features