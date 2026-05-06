from fastapi import FastAPI, Request, Query, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
from sqlalchemy import text, select
from urllib.parse import unquote
import os
import base64
import time
import secrets
import string

from app.models import Base, User, Playlist, Channel
from app.api.router import router as api_router

# ==========================================
# 🔧 DATABASE SETUP
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set!")

engine = create_async_engine(
    DATABASE_URL,
    connect_args={"ssl": True} if "postgresql" in DATABASE_URL else {},
    echo=False,
    pool_pre_ping=True
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except:
            await session.rollback()
            raise
        finally:
            await session.close()

# ==========================================
# 🔄 LIFESPAN — ИСПРАВЛЕНО! БЕЗ DROP TABLE!
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting JFork IPTV Backend...")
    
    # ✅ Только создание таблиц, БЕЗ УДАЛЕНИЯ!
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Tables ready")
    
    yield
    await engine.dispose()
    print("🔌 Database disconnected")

# ==========================================
# 🎯 APP INIT
# ==========================================
app = FastAPI(title="JFork IPTV", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутер API
app.include_router(api_router, prefix="/api/v1")

# Создаем папку для статики
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
# 🔑 УТИЛИТА: ГЕНЕРАЦИЯ КОРОТКОГО ТОКЕНА
# ==========================================
def generate_playlist_token(length: int = 10) -> str:
    """Генерирует токен как у konkurentov: abc123def4"""
    chars = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

# ==========================================
# 📺 IPTV ENDPOINTS — ПРЯМЫЕ ССЫЛКИ (В main.py для надежности)
# ==========================================

@app.get("/api/v1/playlists/{playlist_id}/get-direct-link")
async def get_direct_playlist_link_main(
    playlist_id: int,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Генерирует/возвращает прямую ссылку на плейлист:
    → /list/abc123def4.m3u
    """
    # Декодируем токен
    try:
        token = authorization.split(" ")[1]
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        email = decoded.split(":")[0]
    except Exception as e:
        print(f"❌ Token decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    
    async with async_session() as session:
        # Ищем пользователя
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        # Проверяем доступ к плейлисту
        result = await session.execute(select(Playlist).where(
            Playlist.id == playlist_id,
            Playlist.owner_email == user.email
        ))
        playlist = result.scalar_one_or_none()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        # Если у пользователя нет токена — генерируем
        if not user.playlist_token:
            while True:
                new_token = generate_playlist_token()
                result = await session.execute(select(User).where(User.playlist_token == new_token))
                if not result.scalar_one_or_none():
                    user.playlist_token = new_token
                    await session.commit()
                    break
        
        # Формируем ссылки
        base_url = os.getenv("BASE_URL", "https://jfork777-iptv-jfork-backend.hf.space")
        direct_link = f"{base_url}/list/{user.playlist_token}.m3u"
        
        return {
            "playlist_id": playlist_id,
            "playlist_name": playlist.name,
            "direct_link": direct_link,
            "token": user.playlist_token,
            "formats": {
                "m3u": f"{base_url}/list/{user.playlist_token}.m3u",
                "m3u8": f"{base_url}/list/{user.playlist_token}.m3u8",
                "alt": f"{base_url}/p/{user.playlist_token}.m3u"
            }
        }

# ✅ Основной формат: /list/TOKEN.m3u или /p/TOKEN.m3u
@app.get("/list/{token}.m3u")
@app.get("/list/{token}.m3u8")
@app.get("/p/{token}.m3u")
@app.get("/p/{token}.m3u8")
async def iptv_with_ext(token: str, db: AsyncSession = Depends(get_db)):
    """Защищенный экспорт по короткому токену"""
    if not token or len(token) < 6:
        raise HTTPException(status_code=404, detail="Invalid token")

    async with async_session() as session:
        # Ищем пользователя по короткому токену
        result = await session.execute(select(User).where(User.playlist_token == token))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Берём первый активный плейлист
        result = await session.execute(
            select(Playlist).where(
                Playlist.owner_email == user.email,
                Playlist.is_active == True
            ).order_by(Playlist.id).limit(1)
        )
        playlist_obj = result.scalar_one_or_none()
        if not playlist_obj:
            raise HTTPException(status_code=404, detail="No active playlist")

        # Получаем каналы
        result = await session.execute(
            select(Channel).where(
                Channel.playlist_id == playlist_obj.id,
                Channel.active == True
            ).order_by(Channel.group_title, Channel.name)
        )
        channels = result.scalars().all()

        if not channels:
            raise HTTPException(status_code=404, detail="Playlist is empty")

        # Формируем M3U
        m3u_lines = ["#EXTM3U"]
        for ch in channels:
            group = ch.group_title or "General"
            name = ch.tvg_name or ch.name
            logo = ch.tvg_logo or ""
            m3u_lines.append(
                f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo}" group-title="{group}",{name}'
            )
            m3u_lines.append(ch.url)

        m3u_content = "\n".join(m3u_lines) + "\n"

        # Ключевые заголовки для IPTV-плееров
        return Response(
            content=m3u_content,
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Content-Disposition": f'inline; filename="{user.email}.m3u"',
                "Cache-Control": "public, max-age=300",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )

# ==========================================
# 🌐 WEB & HEALTH
# ==========================================
@app.get("/")
@app.get("/dashboard")
async def serve(): 
    return FileResponse("static/index.html")

@app.get("/health")
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)

@app.get("/test")
def test_route():
    return {"status": "ok", "message": "✅ Server running!"}