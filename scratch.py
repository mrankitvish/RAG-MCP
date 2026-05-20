from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient

app = FastAPI()

router = APIRouter()
@router.get("/upload")
def upload(): return {"ok": True}

sub_app = FastAPI()
@sub_app.get("/sse")
def sse(): return {"sse": True}

app.include_router(router)
app.mount("/", sub_app)

client = TestClient(app)
print("GET /upload:", client.get("/upload").status_code)
print("GET /sse:", client.get("/sse").status_code)
