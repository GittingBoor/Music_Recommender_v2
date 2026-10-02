from pathlib import Path
from src.youtube.service import YoutubeService
import inspect, src.youtube.service as s
d = Path("/tmp/trimdbg")
svc = [c for n, c in inspect.getmembers(s, inspect.isclass) if hasattr(c, "download_audio")][0]
try:
    p = svc().download_audio("PBHdYm98BHY", d)
except TypeError:
    p = s.YoutubeService().download_audio("PBHdYm98BHY", d)
print("file", p)
from inaSpeechSegmenter import Segmenter
for seg in Segmenter(detect_gender=False)(str(p)):
    print(seg)
