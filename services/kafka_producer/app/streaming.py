from typing import Generator
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import get_current_active_user, User
from .producer import send_message

app = FastAPI()

app.mount("streaming/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Разрешённые источники (CORS)
origins = [
    "http://localhost",
    "http://localhost:8001",  # Auth Service
    "http://localhost:8002",  # Streaming Service
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

files = {
    item: os.path.join("samples_directory", item)
    for item in os.listdir("samples_directory")
}

# Генерация чанков для стриминга
def file_chunk_generator(file_path: str, chunk_size: int = 512 * 512) -> Generator[bytes, None, None]:
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            yield chunk

# Эндпоинт для стриминга видео (защищённый JWT)
@app.get("/get_video/{video_name}", response_class=StreamingResponse, responses={
    200: {"content": {"video/mp4": {}}},
    404: {"description": "Video not found"},
})
async def get_video(video_name: str, request: Request,
                    current_user: User = Depends(get_current_active_user)) -> StreamingResponse:
    video_path = files.get(video_name)
    if video_path:
        user_ip = request.client.host
        message = {
            "event": "video_streamed",
            "video_name": video_name,
            "user": current_user.username,
            "user_ip": user_ip,
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            send_message(message)
        except Exception as e:
            app.logger.error(f"Failed to send Kafka message: {e}")

        return StreamingResponse(file_chunk_generator(video_path), media_type="video/mp4")
    else:
        raise HTTPException(status_code=404, detail="Video not found")

# Эндпоинт для воспроизведения видео через plyr (защищённый JWT)
@app.get("/play_video/plyr/{video_name}", response_class=HTMLResponse)
async def play_video_plyr(video_name: str, request: Request,
                          current_user: User = Depends(get_current_active_user)) -> HTMLResponse:
    video_path = files.get(video_name)
    if video_path:
        return templates.TemplateResponse(
            "play_plyr.html",
            {"request": request, "video": {"path": f"/get_video/{video_name}", "name": video_name}}
        )
    else:
        raise HTTPException(status_code=404, detail="Video not found")

# Список всех доступных видео (защищённый JWT)
@app.get("/", response_class=HTMLResponse)
async def videos_list(request: Request, current_user: User = Depends(get_current_active_user)) -> HTMLResponse:
    return templates.TemplateResponse("videos_list.html", {"request": request, "files": files, "user": current_user})

# Проверка работоспособности
@app.get("/ping", response_model=dict)
async def ping_pong():
    return {"message": "pong"}
