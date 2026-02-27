from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import uvicorn
import json

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

app.mount("/static", StaticFiles(directory=DATA_DIR), name="static")

@app.get("/getjson/{filename}")
def get_json(filename: str):
    file_path = os.path.join(DATA_DIR, filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return JSONResponse(content=data)

@app.get("/")
def read_root():
    return {"message": "API don't work"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)