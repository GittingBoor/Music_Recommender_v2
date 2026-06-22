from pydub import AudioSegment
import pathlib
import os
import librosa
from config_audio import temp_folder
from audio_process_base import AudioProcess

class AudioFromWebProcess(AudioProcess):
    
    def __init__(self, formData, statistics=True, frames=True):
        self.file_path = temp_folder + formData.filename
        self.filename = formData.filename
        self.audio = formData.file
        self.statistics = statistics
        self.frames = frames
        
    def formData_to_disc(self):
        audio_format = pathlib.Path(self.file_path).suffix.split('.')[1] # mp3, wav, etc.
        audio = AudioSegment.from_file(self.audio, format=str(audio_format))
        audio.export(self.file_path, format=str(audio_format))
        self.audio = librosa.load(self.file_path, sr=self.sr)[0]

    def remove_audio_from_disc(self):
        os.remove(self.file_path)
