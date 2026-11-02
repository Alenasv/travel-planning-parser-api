import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
PLACES_IMAGES_DIR = DATA_DIR / "places_images"
GEOAPIFY_IMAGES_DIR = DATA_DIR / "geoapify_images"

ALL_PLACES_FILE = DATA_DIR / "all_places.json"

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
RELOAD_MODEL_TIMEOUT = int(os.getenv("RELOAD_MODEL_TIMEOUT", "300"))

GEOAPIFY_PER_CATEGORY = int(os.getenv("GEOAPIFY_PER_CATEGORY", "2"))
GEOAPIFY_AREA = os.getenv("GEOAPIFY_AREA", "center")
GEOAPIFY_REQUIRE_DETAILS = (
    os.getenv("GEOAPIFY_REQUIRE_DETAILS", "true").lower() == "true"
)

PETERBURG_PER_CATEGORY = int(os.getenv("PETERBURG_PER_CATEGORY", "2"))
PETERBURG_BASE_URL = os.getenv(
    "PETERBURG_BASE_URL",
    "https://peterburg.center"
)

PARSER_REQUEST_TIMEOUT = int(os.getenv("PARSER_REQUEST_TIMEOUT", "15"))
GEOAPIFY_REQUEST_TIMEOUT = int(os.getenv("GEOAPIFY_REQUEST_TIMEOUT", "60"))

GEOAPIFY_GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
GEOAPIFY_REVERSE_URL = "https://api.geoapify.com/v1/geocode/reverse"
GEOAPIFY_SPB_FILTER = "rect:29.42,59.63,30.76,60.25"
GEOAPIFY_GEOCODE_TIMEOUT = int(
    os.getenv("GEOAPIFY_GEOCODE_TIMEOUT", "20")
)

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_USER_AGENT = "places-recommender/1.0"
NOMINATIM_TIMEOUT = int(os.getenv("NOMINATIM_TIMEOUT", "10"))
NOMINATIM_MIN_INTERVAL = float(
    os.getenv("NOMINATIM_MIN_INTERVAL", "1.1")
)

IMAGE_DOWNLOAD_TIMEOUT = int(
    os.getenv("IMAGE_DOWNLOAD_TIMEOUT", "30")
)

GEOAPIFY_KEY = os.getenv("GEOAPIFY_KEY")
