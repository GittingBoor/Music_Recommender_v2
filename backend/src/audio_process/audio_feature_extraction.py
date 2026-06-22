from essentia.standard import MusicExtractor, Extractor, TempoCNN, TensorflowPredictMusiCNN, YamlOutput, MonoLoader, PoolAggregator
import numpy as np
import librosa
import os
import json
from collections import Counter
from pandas import DataFrame
import tensorflow as tf
import sys
import statistics
import config_audio as config
import gmbi_util as gmbi_util
import joblib
import warnings
import math
import random
warnings.simplefilter(action='ignore')
from essentia import log
log.warningActive = False

sys.path.append(config.working_dir + '/src/')  
from msa.msa import MusicStructureAnalysis

# load random forests and store to dict
random_forest = {}
for key in config.gmbi_rf_models:
    random_forest[key] = joblib.load(config.gmbi_rf_models[key])
    print('loaded Random Forest Models: ', key)

class AudioFeatureExtraction():

    sr = 44100
    hopSize = 1024
    frameSize = 2048
    statistic_values = ['mean', 'stdev', 'min', 'max', 'median'] #'dmean', 'dmean2', 'dvar', 'dvar2'

    def __init__(self, file_path):
        self.file_path = file_path
        self.audio = MonoLoader(filename=self.file_path, sampleRate=self.sr)()
        self.duration = len(self.audio) / float(self.sr)

    def get_duration(self):
        return len(self.audio) / float(self.sr)
    
    def scale_gmbi_values(self, A):
        return (A-np.min(A))/(np.max(A) - np.min(A))

    def compute_rms(self):
        return np.mean(librosa.feature.rms(y=self.audio, frame_length=self.frameSize, hop_length=self.hopSize))
    
    def pool_to_json(self, pool):
        YamlOutput(filename = 'essentiaFeatures.json', format='json', writeVersion=False)(pool)
        with open('essentiaFeatures.json') as file:
            features = json.load(file)
        os.remove('essentiaFeatures.json')
        return features

    def extract_essentia_features(self):
        features = {}
        features_statistics, features_frames = MusicExtractor(lowlevelStats=self.statistic_values, 
                                                                rhythmStats=self.statistic_values, 
                                                                tonalStats=self.statistic_values,
                                                                analysisSampleRate=self.sr, 
                                                                lowlevelHopSize=self.hopSize, lowlevelFrameSize=self.frameSize, 
                                                                tonalHopSize=self.hopSize, tonalFrameSize=self.frameSize)(self.file_path)

        # convert pool to json and store to dict
        features['statistics'] = self.pool_to_json(features_statistics)
        features['frames'] = self.pool_to_json(features_frames)
    
        return features

    def extract_essentia_dl_features(self, gmbi_inference=False):

        features = {'mean':{}, 'frames':{}, 'dl_gmbi_inference_features':[]}  

        # resample audio. BPM CNN works with 11khz, other CNNs with 16 khz
        audio_11khz = librosa.resample(self.audio, orig_sr=self.sr, target_sr=11025)
        audio_16khz = librosa.resample(self.audio, orig_sr=self.sr, target_sr=16000)

        for model in config.ml_models:
            
            if model == 'genre': continue
            if model != 'bpm':
                if model == 'voice': get_predicted_class = 1
                else: get_predicted_class = 0
                
                predictions  = TensorflowPredictMusiCNN(graphFilename=config.ml_models[model])(audio_16khz)
                features['mean'][model] = np.around(np.mean(predictions, axis=0)[get_predicted_class], decimals=8).tolist()
                features['frames'][model] = np.around(predictions[:, get_predicted_class].astype(float), decimals=8).tolist()

                # stores both classes for gmbi inference
                if model != 'tonal':
                    features['dl_gmbi_inference_features'].extend(np.around(np.mean(predictions, axis=0), decimals=8).tolist())
     
            else:
                global_bpm = TempoCNN(graphFilename=config.ml_models[model])(audio_11khz)[0]
                features['mean'][model] = round(float(global_bpm), 2)

                # storing for gmbi inference
                features['dl_gmbi_inference_features'].extend([features['mean'][model]])
        
        if gmbi_inference == False:
            return {key: features[key] for key in ['mean', 'frames']}
        else:
            return features

    def extract_essentia_genre_features(self):
    
        features = {'all_genres': {}, 'top3_genres': {}, 'top3_genres_frames': {}}  
        audio_16khz = librosa.resample(self.audio, orig_sr=self.sr, target_sr=16000)
        predictions = TensorflowPredictMusiCNN(graphFilename=config.ml_models['genre'])(audio_16khz)
        
        predictions_mean = np.array(np.around(np.mean(predictions, axis=0).astype(float), decimals=8))
        # delete unecessary genres, that are not part of the webApp; to see which check config_file.py
        indexes = [5, 7, 10, 13, 17, 19, 21, 25, 31, 32, 34, 35, 38, 39, 44, 47, 49]

        predictions_mean = np.delete(predictions_mean, indexes)
        predictions = np.delete(predictions, indexes, axis=1)
 
        for i, name in enumerate(config.genres):
            features['all_genres'][name] = predictions_mean[i]

        for name in Counter(features['all_genres']).most_common(3):
            features['top3_genres'][name[0]] = name[1]
            index = list(features['all_genres'].keys()).index(name[0])
            features['top3_genres_frames'][name[0]] = np.around(np.array(predictions[:, index], dtype=float), decimals=8).tolist()

        return features
    
    def extract_gmbi_features_frames(self, essentia_dl_features=None):

        print('computing GMBI features...', flush=True)

        gmbi_data = {'mean':{}, 'frames':{'valence':[], 'arousal':[], 'authenticity':[], 'timeliness':[], 'complexity':[]}}

        if essentia_dl_features is None:
            essentia_dl_features = self.extract_essentia_dl_features()['frames']
        else:
            essentia_dl_features = essentia_dl_features['frames']

        num_dl_predictions = len(essentia_dl_features['voice'])
        num_samples_pro_prediction = int(math.ceil((len(self.audio)/num_dl_predictions)))

        for i, start in enumerate(range(0, len(self.audio), num_samples_pro_prediction)):
            audio_chunk = self.audio[start:start+num_samples_pro_prediction]
            features = Extractor()(audio_chunk)
            features = self.pool_to_json(PoolAggregator(defaultStats = ['min', 'max', 'median', 'mean', 'stdev'])(features))
            
            dl_dict = {}
            for key in essentia_dl_features.keys():
                if key == 'bpm':
                    continue
                dl_dict[key] = essentia_dl_features[key][i]

            df = gmbi_util.create_gmbi_df(features, dl_dict)
            data = np.array(df).reshape(1,-1)

            # run inference
            try:
                for key in config.gmbi_rf_models.keys():
                    prediction = random_forest[key].predict(data)
                    gmbi_data['frames'][key].append(round(prediction[0], 8))
            except Exception as e:
                for key in config.gmbi_rf_models.keys():
                    gmbi_data['frames'][key].append(random.uniform(-2, 2))
                with open(config.path + '/gmbi_error.txt', 'a') as f:
                    f.write(self.file_path + '\n')
                    f.write(str(e) + '\n\n')
        
        # create random list of len num_dl_predictions (faster for debugging)
        # for key in config.gmbi_rf_models.keys():
        #     random_list = [random.uniform(-2, 2) for _ in range(num_dl_predictions)]
        #     gmbi_data['frames'][key] = random_list

        # compute mean  
        for key in config.gmbi_rf_models.keys():
            gmbi_data['mean'][key] = statistics.mean(gmbi_data['frames'][key])
        
        return gmbi_data

    def extract_gmbi_features(self, essentia_features=None, essentia_dl_features=None):

        gmbi_inference_data = []
        features = {'mean': {}, 'frames':{}}
        
        if essentia_features is None: 
            essentia_features = self.extract_essentia_features()['statistics']
        else:
             essentia_features = essentia_features['statistics']
        if essentia_dl_features is None:
            essentia_dl_features = self.extract_essentia_dl_features(gmbi_inference=True)['dl_gmbi_inference_features']
        else:
            essentia_dl_features = essentia_dl_features['dl_gmbi_inference_features']

        # get MusicExtractor features
        for i in config.featuresMusicExtractor:
            [a, b, c] = i.split('.')
            if [a, b, c] == ['lowlevel', 'mfcc', 'mean']:
                for m in range(0, 13):
                    mfcc = essentia_features[a][b][c][m]
                    gmbi_inference_data.append(mfcc)
            else:
                gmbi_inference_data.append(essentia_features[a][b][c])

        gmbi_inference_data.append(self.compute_rms())
        gmbi_inference_data.extend(essentia_dl_features)

        # calculate zscore based on gmbi training set
        gmbi_inference_data = (gmbi_inference_data - np.array(config.gmbi_train_mean))/np.array(config.gmbi_train_stdv)
        gmbi_inference_data = DataFrame([gmbi_inference_data], columns=config.gmbi_inference_features)       

        # run inference
        for model in config.gmbi_models:
            gmbi = tf.keras.models.load_model(config.gmbi_models[model])
            prediction = gmbi.predict(gmbi_inference_data).flatten()
            features['mean'][model] = prediction.astype(float)[0]

        return features

    def extract_all_features(self, statistics=True, frames=False):
        all_features = {'statistics':{}, 'frames':{}, 'songStructure':{}}

        essentia_features = self.extract_essentia_features()
        essentia_dl_features = self.extract_essentia_dl_features(gmbi_inference=True)
        #gmbi_features = self.extractgmbi_features(essentia_features=essentia_features, essentia_dl_features=essentia_dl_features)
        gmbi_features = self.extract_gmbi_features_frames(essentia_dl_features=essentia_dl_features)
        genres = self.extract_essentia_genre_features()
        print('computing MSA...', flush=True)
        boundaries, labels = MusicStructureAnalysis(self.file_path).process_boundaries_labels()

        if statistics == True:
            all_features['statistics']['essentiaFeatures_Statistics'] = essentia_features['statistics']
            all_features['statistics']['essentiaFeatures_DL_Mean'] = essentia_dl_features['mean']
            all_features['statistics']['gmbiFeatures'] = gmbi_features['mean']
            all_features['statistics']['genres'] = {'all_genres': genres['all_genres'], 'top3_genres': genres['top3_genres']}
        else:
            del all_features['statistics']
            
        if frames == True: 
            all_features['frames']['essentiaFeatures_Frames'] = essentia_features['frames']
            all_features['frames']['essentiaFeatures_DL_Frames'] = essentia_dl_features['frames']
            all_features['frames']['gmbiFeatures_Frames'] = gmbi_features['frames']
            all_features['frames']['top3_genres_frames'] = genres['top3_genres_frames']
        else:
            del all_features['frames']

        all_features['songStructure']['boundaries'] = boundaries
        all_features['songStructure']['labels'] = labels

        return all_features
    

    def extract_aim_features(self, gmbi_model='rf'):
        aim_features = {'features':{}, 'features_frames':{}, 'songStructure':{}}
        essentia_dl_features = self.extract_essentia_dl_features(gmbi_inference=True)
        if gmbi_model == 'rf': 
            gmbi_features = self.extract_gmbi_features_frames(essentia_dl_features=essentia_dl_features)
        if gmbi_model == 'nn': 
            gmbi_features = self.extract_gmbi_features(essentia_dl_features=essentia_dl_features)
        genres = self.extract_essentia_genre_features()
        print('computing MSA...', flush=True)
        boundaries, labels = MusicStructureAnalysis(self.file_path).process_boundaries_labels()

        aim_features['features']= gmbi_features['mean']
        aim_features['features'].update(essentia_dl_features['mean'])
        aim_features['features']['genres'] = {'all_genres': genres['all_genres'], 'top3_genres': genres['top3_genres']}
        aim_features['features_frames']['highLevel_graphs'] = gmbi_features['frames']
        aim_features['features_frames']['highLevel_graphs'].update(essentia_dl_features['frames'])
        aim_features['features_frames']['top3_genre_graphs'] = genres['top3_genres_frames']

        aim_features['songStructure']['boundaries'] = boundaries
        aim_features['songStructure']['labels'] = labels

        return aim_features

    @classmethod
    def set_fft_features(cls, sr=48000, hopSize=512, frameSize=1024):
        cls.sr = sr
        cls.hopSize = hopSize
        cls.frameSize = frameSize

    @classmethod
    def set_statistics(cls, statistics):
        cls.statistics = statistics

# gives a single float value
# a = AudioFeatureExtraction('/Users/maed/Desktop/BA_Fiedler/AudioFiles/Music_30sec/0001.mp3')
# a.extract_aim_features()



