from fastapi import FastAPI, APIRouter
from fastapi.staticfiles import StaticFiles
import os

os.makedirs("dummy_static", exist_ok=True)
with open("dummy_static/test.txt", "w") as f:
    f.write("hello")

app = FastAPI()
router = APIRouter(prefix="/upload")

try:
    router.mount("/static", StaticFiles(directory="dummy_static"))
    print("Router has mount!")
except Exception as e:
    print("Error:", e)

app.include_router(router)
print("Routes:", [r.path for r in app.routes])

from fastapi.testclient import TestClient
client = TestClient(app)
print("GET /upload/static/test.txt:", client.get("/upload/static/test.txt").status_code)
