import os
import traceback
import gc
from audio_process_base import AudioProcess
from config_audio import json_folder, music_to_process_folder, path, json_folder_no_db

def single_file(file_path='/Users/maed/Desktop/0007.mp3'):
    audio = AudioProcess(file_path=file_path)
    aim_db_features = audio.compute_aim_features()
    print(aim_db_features)

def iterate_folder():
    for subdir, dirs, files in os.walk(music_to_process_folder):
        dirs.sort()
        files.sort()    
        for file in files:
            file_path = os.path.join(subdir, file)
            if file_path.endswith(tuple(['.mp3', '.wav', 'aiff'])):
                try:
                    file_name = file_path.split('/')[-1].split('.')[0] 
                    album_name = subdir.split('/')[-1]
                    artist_name = subdir.split('/')[-2]

                    audio = AudioProcess(file_path=file_path)
                    metadata = {'album': album_name, 'artist': artist_name}
                    
                    # store to db and to json
                    aim_db_features = audio.compute_aim_features(metadata)
                    # audio.store_to_json(json_path=json_folder_no_db, features=aim_db_features, metadata=metadata)
                    #ids = audio.store_to_db(features=aim_db_features)

                    # store to json with db ids
                    #aim_db_features['ids'] = ids
                    #audio.store_to_json(json_path=json_folder, features=aim_db_features, metadata=metadata)
                    
                    print('Done: ', file_name + ' - ' + album_name + ' - ' + artist_name, flush=True)
                    print('\n', flush=True)

                    del audio
                    gc.collect()


                except Exception as e:
                    file_error = file_name + ' - ' + album_name + ' - ' + artist_name
                    with open(path + '/error.txt', 'a') as f:
                        f.write(file_error + '\n')
                        f.write(str(traceback.format_exc()) + '\n\n')

single_file()