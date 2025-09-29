from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from ..routers.tasks import get_current_user_id

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/lists", response_class=HTMLResponse)
async def lists_page(request: Request, user_id: int = Depends(get_current_user_id)):
    if user_id is None:
        return RedirectResponse(url="/login", status_code=302)
    
    return templates.TemplateResponse("lists.html", {"request": request})