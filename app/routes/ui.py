from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/ui", response_class=HTMLResponse)
async def ui_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
