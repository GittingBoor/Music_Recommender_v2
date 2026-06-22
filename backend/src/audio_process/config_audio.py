working_dir = '/Users/maed/Documents/Projects/AIM/audio_process'
path = '/Users/maed/Desktop/Backend_AudioProcess'

# working_dir = '/app'
# path = '/data'

db_audio_folder = path + '/DB_Audio'
music_to_process_folder = path + '/Music_To_Process'
temp_folder = path + '/temp/'
json_folder = path + '/jsonFiles/'
json_folder_no_db = path + '/jsonFilesNoDB/'
server_folder = path + '/serverFolder/'
pdf_folder = path + '/pdfFiles/'

ml_models = {  
    "bpm": path + '/Models/deeptemp-k16-3.pb',
    "voice": path + '/Models/voice_instrumental-musicnn-msd-2.pb', # voice[1]
    "female": path + '/Models/gender-musicnn-msd-2.pb', # female[0] 
    "danceability": path + '/Models/danceability-musicnn-msd-2.pb', # danceable[0]
    "tonal": path + '/Models/tonal_atonal-musicnn-msd-2.pb', # tonal[0]
    "genre": path + '/Models/msd-musicnn-1.pb'
}

gmbi_rf_models = {
    "valence": path + '/Models/gmbi_rf/valence_noBeat.joblib',
    "arousal": path + '/Models/gmbi_rf/arousal_noBeat.joblib',
    "authenticity": path + '/Models/gmbi_rf/authenticity_noBeat.joblib',
    "timeliness": path + '/Models/gmbi_rf/timeliness_noBeat.joblib',
    "complexity": path + '/Models/gmbi_rf/complexity_noBeat.joblib',
}

gmbi_models = {
    "valence": path + '/Models/gmbi_old_nn/valence',
    "arousal": path + '/Models/gmbi_old_nn/arousal',
    "authenticity": path + '/Models/gmbi_old_nn/authenticity',
    "timeliness": path + '/Models/gmbi_old_nn/timeliness',
    "complexity": path + '/Models/gmbi_old_nn/complexity'
}

# not used genres from msd:
["female vocalists", "00s", "beautiful", "male vocalists", "Mellow", "80s", "90s", "oldies", "female vocalist", "guitar", "70s", "party", "sexy", "catchy", "60s","sad", "happy"]

# used genres from msd:
genres = ["rock", "pop", "alternative", "indie", "electronic", "dance",
            "alternative rock", "jazz", "metal", "chillout", "classic rock", "soul", "indie rock", "electronica", "folk", 
            "chill", "instrumental", "punk", "blues", "hard rock", "ambient", "acoustic", "experimental",
            "Hip-Hop", "country", "easy listening", "funk", "electro", "heavy metal", "Progressive rock", 
            "rnb", "indie pop", "House"]

# GMBI inference features from MusicExtractor 
featuresMusicExtractor = [
    'lowlevel.spectral_centroid.max', 'lowlevel.spectral_centroid.min', 'lowlevel.spectral_centroid.median', 'lowlevel.spectral_centroid.mean', 'lowlevel.spectral_centroid.stdev',
    'lowlevel.spectral_rolloff.max', 'lowlevel.spectral_rolloff.min', 'lowlevel.spectral_rolloff.median', 'lowlevel.spectral_rolloff.mean', 'lowlevel.spectral_rolloff.stdev',
    'lowlevel.spectral_flux.max', 'lowlevel.spectral_flux.min', 'lowlevel.spectral_flux.median', 'lowlevel.spectral_flux.mean', 'lowlevel.spectral_flux.stdev',
    'lowlevel.melbands_crest.max', 'lowlevel.melbands_crest.min', 'lowlevel.melbands_crest.median', 'lowlevel.melbands_crest.mean', 'lowlevel.melbands_crest.stdev',
    'lowlevel.mfcc.mean'
]

# additional features, that are not in Essentias MusicExtractor (13 mfccs are in MusicExtractor, but are getting individual names here)
featuresAdditional = ['mfcc_1', 'mfcc_2', 'mfcc_3', 'mfcc_4', 'mfcc_5', 'mfcc_6', 'mfcc_7', 'mfcc_8',
                      'mfcc_9', 'mfcc_10', 'mfcc_11', 'mfcc_12', 'mfcc_13',
                      'rmsWaveForm', 'bpm', 'danceable', 'voice', 'tonal', 'female']

merge_features = [*featuresMusicExtractor, *featuresAdditional]
gmbi_inference_features = merge_features.remove('lowlevel.mfcc.mean')

# z-Standardisierung from GMBI Training dataset
gmbi_train_mean = [4304.467516882324, 261.74677831573484, 1260.9834733947755, 1359.8331622497558, 635.9399246307373, 10285.1708203125, 80.66337890625,
        1028.98564453125, 1520.3353218078614, 1634.8734796264648, 0.39592601194083693, 0.000708590870954787, 0.08244796831775457, 0.10030800342559815,
        0.06753226600438356, 33.117014208221434, 4.244641485500336, 16.40874999732971, 16.9565301448822, 6.161106257915497, -656.0196318847657,
        118.92494503326417, 10.447095110334455, 21.845709711566567, 7.000801872124336, 6.495225010318309, 2.651624589442462, 5.124417172216624,
        1.2524997454084457, 3.597588812500582, 0.1687594781305641, 0.8034831906133332, -0.28256157128149645, 0.21183581947386265, 116.5172, 0.20131734738808008,
        0.7907550511702895, 0.44773288787677884, 0.5534380101077025, 0.7113106577267405, 0.28381864464345935]

gmbi_train_stdv = [1384.9670265215545, 183.2666812918937, 519.4086411089112, 459.9783269373903, 219.80002148102415, 3148.929935868467, 43.404677893428534,
        680.2361034285709, 710.1270314805328, 771.7700180865388, 0.11644394110959715, 0.00038664404428150745, 0.02231384189017726, 0.02255657241125257,
        0.02228985539668799, 3.4861420970718413, 1.2034036918184805, 4.198400071505198, 3.6131573724981783, 1.536543218984324, 59.07438977889181,
        35.52153093715034, 21.94055368632451, 13.469497097426842, 9.708297172352388, 9.344183931551497, 8.21357488329068, 6.930678857265335,
        6.273217794176767, 5.53465714477443, 5.1220975016929025, 4.672487099095496, 4.460216908839947, 0.052428397131584974, 24.295433812961722,
        0.25085396280902705, 0.2593542864541213, 0.28159425945911337, 0.2810039921374059, 0.3499780226533626, 0.34698674540391083]
