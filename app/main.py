from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await init_db()

@app.get("/")
async def root():
    return {"status": "Bingo Backend Online"}

# We will add game logic here later!
