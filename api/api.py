from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from api.schemas import RecommendRequest
from ml.model import PlacesRecommender
from contextlib import asynccontextmanager
import json
import os
import uvicorn


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

model = None


def load_places():
    path = os.path.join(DATA_DIR, "all_places.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    places = load_places()
    model = PlacesRecommender(places)
    yield


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory=DATA_DIR), name="static")

@app.get("/getjson/{filename}")
def get_json(filename: str):
    file_path = os.path.join(DATA_DIR, filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return JSONResponse(content=data)

@app.post("/recommend")
def recommend(req: RecommendRequest):

    recs = model.recommend(req.user_preferences, req.top_k)

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
    return {"message": "API don't work"}

@app.get("/clusters")
def get_clusters():
    return {
        "clusters": model.build_clusters()
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

