from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
import os

from .routers import auth, tasks, general

os.chdir(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI()

# --- Static Files ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Include Routers ---
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(general.router)

# --- Favicon ---
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)