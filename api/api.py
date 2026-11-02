import logging
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from api.schemas import RecommendRequest
from ml.model import PlacesRecommender
from contextlib import asynccontextmanager
from db.database import get_all_places, get_all_metro_stations
import uvicorn

from config import DATA_DIR, API_HOST, API_PORT

model = None

logger = logging.getLogger(__name__)
@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    places = get_all_places()

    if not places:
        raise RuntimeError("В PostgreSQL нет мест для загрузки ML-модели")

    model = PlacesRecommender(places)
    yield


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(DATA_DIR)), name="static")


@app.post("/recommend")
def recommend(req: RecommendRequest):
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="ML-модель ещё не загружена"
        )
    top_k = max(1, min(req.top_k, 10))  

    recs = model.recommend(
        user_preferences=req.user_preferences,
        metro_name=req.start_metro,
        top_k=top_k
    )

    return {
        "places": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "category": p.get("category"),
                "metro": p.get("metro"), 
                "address": p.get("address"),
                "work_time": p.get("work_time", "")
            }
            for p in recs
        ]
    }
@app.get("/")
def read_root():
    return {
        "message": "Travel Recommendation API",
        "status": "running"
    }

@app.get("/metro-stations")
def get_metro_stations():
    stations = get_all_metro_stations()
    return {"stations": stations}

@app.get("/clusters")
def get_clusters():
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="ML-модель ещё не загружена"
        )

    return {
        "clusters": model.build_clusters()
    }



@app.post("/reload-model")
def reload_model():
    global model

    places = get_all_places()

    if not places:
        raise HTTPException(
            status_code=400,
            detail="В PostgreSQL нет мест для загрузки модели"
        )

    try:
        new_model = PlacesRecommender(places)
        model = new_model

        return {
            "status": "success",
            "message": "ML-модель успешно обновлена",
            "places_count": len(new_model.places)
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обновления ML-модели: {str(e)}"
        )




@app.get("/places")
def get_places():
    places = get_all_places()
    return {"places": places}

@app.get("/ping")
def ping():
    return {"status": "ok"}
    
if __name__ == "__main__":
    uvicorn.run(app, host=API_HOST, port=API_PORT)

