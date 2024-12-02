import os
from typing import Generator

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()

app.mount("static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Разрешённые источники (CORS)
origins = [
    "http://localhost",
    "http://localhost:5000",
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

# Эндпоинт для стриминга видео
@app.get("/get_video/{video_name}", response_class=StreamingResponse, responses={
    200: {"content": {"video/mp4": {}}},  # Указание MIME-типа
    404: {"description": "Video not found"},
})
async def get_video(video_name: str) -> StreamingResponse:
    video_path = files.get(video_name)
    if video_path:
        return StreamingResponse(file_chunk_generator(video_path), media_type="video/mp4")
    else:
        raise HTTPException(status_code=404, detail="Video not found")

# Эндпоинт для воспроизведения видео через plyr
@app.get("/play_video/plyr/{video_name}", response_class=HTMLResponse)
async def play_video_plyr(video_name: str, request: Request) -> HTMLResponse:
    video_path = files.get(video_name)
    if video_path:
        return templates.TemplateResponse(
            "play_plyr.html", {"request": request, "video": {"path": video_path, "name": video_name}}
        )
    else:
        raise HTTPException(status_code=404, detail="Video not found")

# Список всех доступных видео
@app.get("/", response_class=HTMLResponse)
async def videos_list(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("videos_list.html", {"request": request, "files": files})

# Проверка работоспособности
@app.get("/ping", response_model=dict)
async def ping_pong():
    return {"message": "pong"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=5000, reload=True)
