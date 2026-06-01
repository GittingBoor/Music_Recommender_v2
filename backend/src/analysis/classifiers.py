import logging

import numpy as np
import essentia.standard as es

from src.analysis.model_manager import get_manager

logger = logging.getLogger(__name__)

_TF1_INPUT = "model/Placeholder"
_TF2_INPUT = "serving_default_model_Placeholder"
_TF2_OUTPUT = "PartitionedCall"

_LAYER_OVERRIDES: dict[str, tuple[str, str]] = {
    "genre_discogs400": (_TF2_INPUT, _TF2_OUTPUT),
}

_GENRE_LABELS: list[str] = [
    "Blues---Boogie Woogie", "Blues---Chicago Blues", "Blues---Country Blues",
    "Blues---Delta Blues", "Blues---Electric Blues", "Blues---Harmonica Blues",
    "Blues---Jump Blues", "Blues---Louisiana Blues", "Blues---Modern Electric Blues",
    "Blues---Piano Blues", "Blues---Rhythm & Blues", "Blues---Texas Blues",
    "Brass & Military---Brass Band", "Brass & Military---Marches", "Brass & Military---Military",
    "Children's---Educational", "Children's---Nursery Rhymes", "Children's---Story",
    "Classical---Baroque", "Classical---Choral", "Classical---Classical",
    "Classical---Contemporary", "Classical---Impressionist", "Classical---Medieval",
    "Classical---Modern", "Classical---Neo-Classical", "Classical---Neo-Romantic",
    "Classical---Opera", "Classical---Post-Modern", "Classical---Renaissance",
    "Classical---Romantic", "Electronic---Abstract", "Electronic---Acid",
    "Electronic---Acid House", "Electronic---Acid Jazz", "Electronic---Ambient",
    "Electronic---Bassline", "Electronic---Beatdown", "Electronic---Berlin-School",
    "Electronic---Big Beat", "Electronic---Bleep", "Electronic---Breakbeat",
    "Electronic---Breakcore", "Electronic---Breaks", "Electronic---Broken Beat",
    "Electronic---Chillwave", "Electronic---Chiptune", "Electronic---Dance-pop",
    "Electronic---Dark Ambient", "Electronic---Darkwave", "Electronic---Deep House",
    "Electronic---Deep Techno", "Electronic---Disco", "Electronic---Disco Polo",
    "Electronic---Donk", "Electronic---Downtempo", "Electronic---Drone",
    "Electronic---Drum n Bass", "Electronic---Dub", "Electronic---Dub Techno",
    "Electronic---Dubstep", "Electronic---Dungeon Synth", "Electronic---EBM",
    "Electronic---Electro", "Electronic---Electro House", "Electronic---Electroclash",
    "Electronic---Euro House", "Electronic---Euro-Disco", "Electronic---Eurobeat",
    "Electronic---Eurodance", "Electronic---Experimental", "Electronic---Freestyle",
    "Electronic---Future Jazz", "Electronic---Gabber", "Electronic---Garage House",
    "Electronic---Ghetto", "Electronic---Ghetto House", "Electronic---Glitch",
    "Electronic---Goa Trance", "Electronic---Grime", "Electronic---Halftime",
    "Electronic---Hands Up", "Electronic---Happy Hardcore", "Electronic---Hard House",
    "Electronic---Hard Techno", "Electronic---Hard Trance", "Electronic---Hardcore",
    "Electronic---Hardstyle", "Electronic---Hi NRG", "Electronic---Hip Hop",
    "Electronic---Hip-House", "Electronic---House", "Electronic---IDM",
    "Electronic---Illbient", "Electronic---Industrial", "Electronic---Italo House",
    "Electronic---Italo-Disco", "Electronic---Italodance", "Electronic---Jazzdance",
    "Electronic---Juke", "Electronic---Jumpstyle", "Electronic---Jungle",
    "Electronic---Latin", "Electronic---Leftfield", "Electronic---Makina",
    "Electronic---Minimal", "Electronic---Minimal Techno", "Electronic---Modern Classical",
    "Electronic---Musique Concrète", "Electronic---Neofolk", "Electronic---New Age",
    "Electronic---New Beat", "Electronic---New Wave", "Electronic---Noise",
    "Electronic---Nu-Disco", "Electronic---Power Electronics", "Electronic---Progressive Breaks",
    "Electronic---Progressive House", "Electronic---Progressive Trance", "Electronic---Psy-Trance",
    "Electronic---Rhythmic Noise", "Electronic---Schranz", "Electronic---Sound Collage",
    "Electronic---Speed Garage", "Electronic---Speedcore", "Electronic---Synth-pop",
    "Electronic---Synthwave", "Electronic---Tech House", "Electronic---Tech Trance",
    "Electronic---Techno", "Electronic---Trance", "Electronic---Tribal",
    "Electronic---Tribal House", "Electronic---Trip Hop", "Electronic---Tropical House",
    "Electronic---UK Garage", "Electronic---Vaporwave",
    "Folk, World, & Country---African", "Folk, World, & Country---Bluegrass",
    "Folk, World, & Country---Cajun", "Folk, World, & Country---Canzone Napoletana",
    "Folk, World, & Country---Catalan Music", "Folk, World, & Country---Celtic",
    "Folk, World, & Country---Country", "Folk, World, & Country---Fado",
    "Folk, World, & Country---Flamenco", "Folk, World, & Country---Folk",
    "Folk, World, & Country---Gospel", "Folk, World, & Country---Highlife",
    "Folk, World, & Country---Hillbilly", "Folk, World, & Country---Hindustani",
    "Folk, World, & Country---Honky Tonk", "Folk, World, & Country---Indian Classical",
    "Folk, World, & Country---Laïkó", "Folk, World, & Country---Nordic",
    "Folk, World, & Country---Pacific", "Folk, World, & Country---Polka",
    "Folk, World, & Country---Raï", "Folk, World, & Country---Romani",
    "Folk, World, & Country---Soukous", "Folk, World, & Country---Séga",
    "Folk, World, & Country---Volksmusik", "Folk, World, & Country---Zouk",
    "Folk, World, & Country---Éntekhno",
    "Funk / Soul---Afrobeat", "Funk / Soul---Boogie", "Funk / Soul---Contemporary R&B",
    "Funk / Soul---Disco", "Funk / Soul---Free Funk", "Funk / Soul---Funk",
    "Funk / Soul---Gospel", "Funk / Soul---Neo Soul", "Funk / Soul---New Jack Swing",
    "Funk / Soul---P.Funk", "Funk / Soul---Psychedelic", "Funk / Soul---Rhythm & Blues",
    "Funk / Soul---Soul", "Funk / Soul---Swingbeat", "Funk / Soul---UK Street Soul",
    "Hip Hop---Bass Music", "Hip Hop---Boom Bap", "Hip Hop---Bounce",
    "Hip Hop---Britcore", "Hip Hop---Cloud Rap", "Hip Hop---Conscious",
    "Hip Hop---Crunk", "Hip Hop---Cut-up/DJ", "Hip Hop---DJ Battle Tool",
    "Hip Hop---Electro", "Hip Hop---G-Funk", "Hip Hop---Gangsta",
    "Hip Hop---Grime", "Hip Hop---Hardcore Hip-Hop", "Hip Hop---Horrorcore",
    "Hip Hop---Instrumental", "Hip Hop---Jazzy Hip-Hop", "Hip Hop---Miami Bass",
    "Hip Hop---Pop Rap", "Hip Hop---Ragga HipHop", "Hip Hop---RnB/Swing",
    "Hip Hop---Screw", "Hip Hop---Thug Rap", "Hip Hop---Trap",
    "Hip Hop---Trip Hop", "Hip Hop---Turntablism",
    "Jazz---Afro-Cuban Jazz", "Jazz---Afrobeat", "Jazz---Avant-garde Jazz",
    "Jazz---Big Band", "Jazz---Bop", "Jazz---Bossa Nova",
    "Jazz---Contemporary Jazz", "Jazz---Cool Jazz", "Jazz---Dixieland",
    "Jazz---Easy Listening", "Jazz---Free Improvisation", "Jazz---Free Jazz",
    "Jazz---Fusion", "Jazz---Gypsy Jazz", "Jazz---Hard Bop",
    "Jazz---Jazz-Funk", "Jazz---Jazz-Rock", "Jazz---Latin Jazz",
    "Jazz---Modal", "Jazz---Post Bop", "Jazz---Ragtime",
    "Jazz---Smooth Jazz", "Jazz---Soul-Jazz", "Jazz---Space-Age", "Jazz---Swing",
    "Latin---Afro-Cuban", "Latin---Baião", "Latin---Batucada",
    "Latin---Beguine", "Latin---Bolero", "Latin---Boogaloo",
    "Latin---Bossanova", "Latin---Cha-Cha", "Latin---Charanga",
    "Latin---Compas", "Latin---Cubano", "Latin---Cumbia",
    "Latin---Descarga", "Latin---Forró", "Latin---Guaguancó",
    "Latin---Guajira", "Latin---Guaracha", "Latin---MPB",
    "Latin---Mambo", "Latin---Mariachi", "Latin---Merengue",
    "Latin---Norteño", "Latin---Nueva Cancion", "Latin---Pachanga",
    "Latin---Porro", "Latin---Ranchera", "Latin---Reggaeton",
    "Latin---Rumba", "Latin---Salsa", "Latin---Samba",
    "Latin---Son", "Latin---Son Montuno", "Latin---Tango",
    "Latin---Tejano", "Latin---Vallenato",
    "Non-Music---Audiobook", "Non-Music---Comedy", "Non-Music---Dialogue",
    "Non-Music---Education", "Non-Music---Field Recording", "Non-Music---Interview",
    "Non-Music---Monolog", "Non-Music---Poetry", "Non-Music---Political",
    "Non-Music---Promotional", "Non-Music---Radioplay", "Non-Music---Religious",
    "Non-Music---Spoken Word",
    "Pop---Ballad", "Pop---Bollywood", "Pop---Bubblegum",
    "Pop---Chanson", "Pop---City Pop", "Pop---Europop",
    "Pop---Indie Pop", "Pop---J-pop", "Pop---K-pop",
    "Pop---Kayōkyoku", "Pop---Light Music", "Pop---Music Hall",
    "Pop---Novelty", "Pop---Parody", "Pop---Schlager", "Pop---Vocal",
    "Reggae---Calypso", "Reggae---Dancehall", "Reggae---Dub",
    "Reggae---Lovers Rock", "Reggae---Ragga", "Reggae---Reggae",
    "Reggae---Reggae-Pop", "Reggae---Rocksteady", "Reggae---Roots Reggae",
    "Reggae---Ska", "Reggae---Soca",
    "Rock---AOR", "Rock---Acid Rock", "Rock---Acoustic",
    "Rock---Alternative Rock", "Rock---Arena Rock", "Rock---Art Rock",
    "Rock---Atmospheric Black Metal", "Rock---Avantgarde", "Rock---Beat",
    "Rock---Black Metal", "Rock---Blues Rock", "Rock---Brit Pop",
    "Rock---Classic Rock", "Rock---Coldwave", "Rock---Country Rock",
    "Rock---Crust", "Rock---Death Metal", "Rock---Deathcore",
    "Rock---Deathrock", "Rock---Depressive Black Metal", "Rock---Doo Wop",
    "Rock---Doom Metal", "Rock---Dream Pop", "Rock---Emo",
    "Rock---Ethereal", "Rock---Experimental", "Rock---Folk Metal",
    "Rock---Folk Rock", "Rock---Funeral Doom Metal", "Rock---Funk Metal",
    "Rock---Garage Rock", "Rock---Glam", "Rock---Goregrind",
    "Rock---Goth Rock", "Rock---Gothic Metal", "Rock---Grindcore",
    "Rock---Grunge", "Rock---Hard Rock", "Rock---Hardcore",
    "Rock---Heavy Metal", "Rock---Indie Rock", "Rock---Industrial",
    "Rock---Krautrock", "Rock---Lo-Fi", "Rock---Lounge",
    "Rock---Math Rock", "Rock---Melodic Death Metal", "Rock---Melodic Hardcore",
    "Rock---Metalcore", "Rock---Mod", "Rock---Neofolk",
    "Rock---New Wave", "Rock---No Wave", "Rock---Noise",
    "Rock---Noisecore", "Rock---Nu Metal", "Rock---Oi",
    "Rock---Parody", "Rock---Pop Punk", "Rock---Pop Rock",
    "Rock---Pornogrind", "Rock---Post Rock", "Rock---Post-Hardcore",
    "Rock---Post-Metal", "Rock---Post-Punk", "Rock---Power Metal",
    "Rock---Power Pop", "Rock---Power Violence", "Rock---Prog Rock",
    "Rock---Progressive Metal", "Rock---Psychedelic Rock", "Rock---Psychobilly",
    "Rock---Pub Rock", "Rock---Punk", "Rock---Rock & Roll",
    "Rock---Rockabilly", "Rock---Shoegaze", "Rock---Ska",
    "Rock---Sludge Metal", "Rock---Soft Rock", "Rock---Southern Rock",
    "Rock---Space Rock", "Rock---Speed Metal", "Rock---Stoner Rock",
    "Rock---Surf", "Rock---Symphonic Rock", "Rock---Technical Death Metal",
    "Rock---Thrash", "Rock---Twist", "Rock---Viking Metal", "Rock---Yé-Yé",
    "Stage & Screen---Musical", "Stage & Screen---Score",
    "Stage & Screen---Soundtrack", "Stage & Screen---Theme",
]

_INSTRUMENT_LABELS: list[str] = [
    "accordion", "acousticbassguitar", "acousticguitar", "bass", "beat",
    "bell", "bongo", "brass", "cello", "clarinet", "classicalguitar",
    "computer", "doublebass", "drummachine", "drums", "electricguitar",
    "electricpiano", "flute", "guitar", "harmonica", "harp", "horn",
    "keyboard", "oboe", "orchestra", "organ", "pad", "percussion",
    "piano", "pipeorgan", "rhodes", "sampler", "saxophone", "strings",
    "synthesizer", "trombone", "trumpet", "viola", "violin", "voice",
]


def _run_classifier_raw(model_key: str, embedding: np.ndarray, output_layer: str) -> np.ndarray:
    """Run a TensorflowPredict2D model and return per-patch predictions (shape: n_patches x n_classes)."""
    path = get_manager().get_path(model_key)
    input_layer, out = _LAYER_OVERRIDES.get(model_key, (_TF1_INPUT, output_layer))
    model = es.TensorflowPredict2D(
        graphFilename=str(path),
        input=input_layer,
        output=out,
    )
    return model(embedding)


def _run_classifier(model_key: str, embedding: np.ndarray, output_layer: str) -> np.ndarray:
    """Run a classifier and return mean predictions across patches."""
    return np.mean(_run_classifier_raw(model_key, embedding, output_layer), axis=0)


def _log(model_key: str, value: object) -> None:
    logger.debug("[Classifier] %s = %s", model_key, value)


def _binary_with_timeseries(model_key: str, embedding: np.ndarray, output_layer: str, positive_index: int = 1) -> dict[str, object]:
    """Run a binary classifier and return mean + per-patch timeseries for the positive class."""
    raw = _run_classifier_raw(model_key, embedding, output_layer)
    timeseries = [round(float(p[positive_index]), 4) for p in raw]
    mean_val = round(float(np.mean(raw, axis=0)[positive_index]), 4)
    return {"mean": mean_val, "timeseries": timeseries}


def _two_class_with_timeseries(
    model_key: str,
    embedding: np.ndarray,
    output_layer: str,
    label_0: str,
    label_1: str,
) -> dict[str, object]:
    """Run a 2-class classifier. Timeseries contains only the dominant class's values."""
    raw = _run_classifier_raw(model_key, embedding, output_layer)
    mean_arr = np.mean(raw, axis=0)
    mean_val = {label_0: round(float(mean_arr[0]), 4), label_1: round(float(mean_arr[1]), 4)}
    dominant_idx = int(np.argmax(mean_arr))
    dominant_label = label_0 if dominant_idx == 0 else label_1
    timeseries = [round(float(p[dominant_idx]), 4) for p in raw]
    return {"mean": mean_val, "dominant": dominant_label, "timeseries": timeseries}


def predict_mood_happy(embedding: np.ndarray) -> dict[str, object]:
    result = _binary_with_timeseries("mood_happy", embedding, "model/Softmax")
    _log("mood_happy", result["mean"])
    return result


def predict_mood_sad(embedding: np.ndarray) -> dict[str, object]:
    result = _binary_with_timeseries("mood_sad", embedding, "model/Softmax")
    _log("mood_sad", result["mean"])
    return result


def predict_mood_aggressive(embedding: np.ndarray) -> dict[str, object]:
    result = _binary_with_timeseries("mood_aggressive", embedding, "model/Softmax")
    _log("mood_aggressive", result["mean"])
    return result


def predict_mood_party(embedding: np.ndarray) -> dict[str, object]:
    result = _binary_with_timeseries("mood_party", embedding, "model/Softmax")
    _log("mood_party", result["mean"])
    return result


def predict_mood_relaxed(embedding: np.ndarray) -> dict[str, object]:
    result = _binary_with_timeseries("mood_relaxed", embedding, "model/Softmax")
    _log("mood_relaxed", result["mean"])
    return result


def predict_mood_acoustic(embedding: np.ndarray) -> dict[str, object]:
    result = _binary_with_timeseries("mood_acoustic", embedding, "model/Softmax")
    _log("mood_acoustic", result["mean"])
    return result


def predict_mood_electronic(embedding: np.ndarray) -> dict[str, object]:
    result = _binary_with_timeseries("mood_electronic", embedding, "model/Softmax")
    _log("mood_electronic", result["mean"])
    return result


def predict_arousal_valence(embedding: np.ndarray) -> dict[str, object]:
    raw = _run_classifier_raw("arousal_valence", embedding, "model/Identity")
    mean_arr = np.mean(raw, axis=0)
    mean_val = {"arousal": round(float(mean_arr[0]), 4), "valence": round(float(mean_arr[1]), 4)}
    timeseries = [{"arousal": round(float(p[0]), 4), "valence": round(float(p[1]), 4)} for p in raw]
    _log("arousal_valence", mean_val)
    return {"mean": mean_val, "timeseries": timeseries}


def predict_genre_discogs400(embedding: np.ndarray) -> dict[str, object]:
    result = _run_classifier("genre_discogs400", embedding, "model/Sigmoid")

    top_indices = np.argsort(result)[::-1][:10].tolist()
    top_genres = [
        {"genre": _GENRE_LABELS[i], "probability": round(float(result[i]), 4)}
        for i in top_indices
    ]

    parent_scores: dict[str, float] = {}
    for i, prob in enumerate(result):
        parent = _GENRE_LABELS[i].split("---")[0]
        parent_scores[parent] = parent_scores.get(parent, 0.0) + float(prob)

    total = sum(parent_scores.values())
    parent_distribution = [
        {"genre": parent, "share": round(score / total, 4)}
        for parent, score in sorted(parent_scores.items(), key=lambda x: x[1], reverse=True)
        if score / total >= 0.01
    ]

    _log("genre_discogs400", f"top={top_genres[0]['genre']}")
    return {"parent_genre_distribution": parent_distribution, "top_10_genres": top_genres}


def predict_approachability(embedding: np.ndarray) -> dict[str, object]:
    result = _two_class_with_timeseries("approachability", embedding, "model/Softmax", "niche", "mainstream")
    _log("approachability", result["mean"])
    return result


def predict_engagement(embedding: np.ndarray) -> dict[str, object]:
    result = _two_class_with_timeseries("engagement", embedding, "model/Softmax", "background", "active")
    _log("engagement", result["mean"])
    return result


def predict_instrument(embedding: np.ndarray) -> dict[str, object]:
    result = _run_classifier("instrument", embedding, "model/Sigmoid")
    top_indices = np.argsort(result)[::-1][:10].tolist()
    top = [
        {"instrument": _INSTRUMENT_LABELS[i], "probability": round(float(result[i]), 4)}
        for i in top_indices
    ]
    _log("instrument", f"top={top[0]['instrument']}")
    return {"top_10": top}


def predict_voice_instrumental(embedding: np.ndarray) -> dict[str, object]:
    result = _two_class_with_timeseries("voice_instrumental", embedding, "model/Softmax", "instrumental", "vocal")
    _log("voice_instrumental", result["mean"])
    return result


def predict_gender(embedding: np.ndarray) -> dict[str, object]:
    result = _two_class_with_timeseries("gender", embedding, "model/Softmax", "female", "male")
    _log("gender", result["mean"])
    return result
