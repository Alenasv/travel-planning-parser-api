import logging
from contextlib import asynccontextmanager
from secrets import compare_digest
from threading import Lock
import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.schemas import RecommendRequest, RecommendResponse
from app.config import API_HOST, API_PORT, DATA_DIR, RELOAD_MODEL_TOKEN
from app.db.database import get_all_metro_stations, get_all_places

model = None
logger = logging.getLogger(__name__)
reload_lock = Lock()
reload_bearer = HTTPBearer(auto_error=False)


def build_recommender(places):
    from app.ml.model import PlacesRecommender

    return PlacesRecommender(places)


def load_places():
    try:
        return get_all_places()
    except Exception:
        logger.exception("Не удалось загрузить места")
        raise HTTPException(status_code=503, detail="База данных недоступна")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    model = None
    places = get_all_places()
    if not places:
        raise RuntimeError("В PostgreSQL нет мест для загрузки ML-модели")
    model = build_recommender(places)
    try:
        yield
    finally:
        model = None


app = FastAPI(lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=str(DATA_DIR), check_dir=False),
    name="static",
)


@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    current_model = model
    if current_model is None:
        raise HTTPException(status_code=503, detail="ML-модель ещё не загружена")
    arguments = {
        "user_preferences": req.user_preferences,
        "metro_name": req.start_metro,
        "top_k": req.top_k,
    }
    if req.user_location is not None:
        arguments["user_location"] = req.user_location.model_dump()
    try:
        recs = current_model.recommend(**arguments)
        return RecommendResponse(
            places=[
                {
                    "id": p["id"],
                    "name": p["name"],
                    "category": p.get("category") or "Без категории",
                    "metro": p.get("metro"),
                    "address": p.get("address"),
                    "work_time": p.get("work_time"),
                }
                for p in recs
            ]
        )
    except Exception:
        logger.exception("Не удалось сформировать рекомендации")
        raise HTTPException(status_code=500, detail="Не удалось сформировать рекомендации")


@app.get("/")
def read_root():
    return {"message": "Travel Recommendation API", "status": "running"}


@app.get("/metro-stations")
def get_metro_stations():
    try:
        stations = get_all_metro_stations()
    except Exception:
        logger.exception("Не удалось загрузить станции метро")
        raise HTTPException(status_code=503, detail="База данных недоступна")
    return {"stations": stations}


@app.get("/clusters")
def get_clusters():
    current_model = model
    if current_model is None:
        raise HTTPException(status_code=503, detail="ML-модель ещё не загружена")
    try:
        clusters = current_model.build_clusters()
        return {
            "clusters": [
                {
                    **cluster,
                    "places": [
                        {key: value for key, value in place.items() if not key.startswith("_")}
                        for place in cluster["places"]
                    ],
                }
                for cluster in clusters
            ]
        }
    except Exception:
        logger.exception("Не удалось загрузить категории")
        raise HTTPException(status_code=500, detail="Не удалось загрузить категории")


def require_reload_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(reload_bearer),
):
    if not RELOAD_MODEL_TOKEN:
        raise HTTPException(status_code=503, detail="Обновление модели не настроено")
    if credentials is None or not compare_digest(
        credentials.credentials.encode("utf-8"), RELOAD_MODEL_TOKEN.encode("utf-8")
    ):
        raise HTTPException(
            status_code=401,
            detail="Неверный служебный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.post("/reload-model", dependencies=[Depends(require_reload_token)])
def reload_model():
    global model
    if not reload_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Обновление модели уже выполняется")
    try:
        places = load_places()
        if not places:
            raise HTTPException(status_code=400, detail="В PostgreSQL нет мест для загрузки модели")
        try:
            new_model = build_recommender(places)
            places_count = len(new_model.places)
        except Exception:
            logger.exception("Ошибка обновления ML-модели")
            raise HTTPException(status_code=500, detail="Ошибка обновления ML-модели")
        model = new_model
        return {
            "status": "success",
            "message": "ML-модель успешно обновлена",
            "places_count": places_count,
        }
    finally:
        reload_lock.release()


@app.get("/places")
def get_places():
    return {"places": load_places()}


@app.get("/ping")
def ping():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host=API_HOST, port=API_PORT)
