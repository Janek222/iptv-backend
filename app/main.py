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
# 🔄 LIFESPAN
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting JFork IPTV Backend...")
    
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

app.include_router(api_router, prefix="/api/v1")

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
# 🔑 TOKEN GENERATOR
# ==========================================
def generate_playlist_token(length: int = 10) -> str:
    chars = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

# ==========================================
# 📺 IPTV ENDPOINTS
# ==========================================

@app.get("/api/v1/playlists/{playlist_id}/get-direct-link")
async def get_direct_playlist_link_main(
    playlist_id: int,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    try:
        token = authorization.split(" ")[1]
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        email = decoded.split(":")[0]
    except Exception as e:
        print(f"❌ Token decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        result = await session.execute(select(Playlist).where(
            Playlist.id == playlist_id,
            Playlist.owner_email == user.email
        ))
        playlist = result.scalar_one_or_none()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        if not user.playlist_token:
            while True:
                new_token = generate_playlist_token()
                result = await session.execute(select(User).where(User.playlist_token == new_token))
                if not result.scalar_one_or_none():
                    user.playlist_token = new_token
                    await session.commit()
                    break
        
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

# ==========================================
# 🔍 DEBUG ENDPOINTS
# ==========================================

@app.get("/list/test")
async def test_list():
    """Проверка что endpoint работает"""
    return {"status": "ok", "message": "List endpoint is working"}

@app.get("/list/check/{token}")
async def check_token(token: str, db: AsyncSession = Depends(get_db)):
    """Проверка токена в базе"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.playlist_token == token))
        user = result.scalar_one_or_none()
        
        if not user:
            return {"found": False, "token": token, "message": "Token not found in database"}
        
        result = await session.execute(
            select(Playlist).where(Playlist.owner_email == user.email)
        )
        playlists = result.scalars().all()
        
        return {
            "found": True,
            "token": token,
            "email": user.email,
            "playlists_count": len(playlists),
            "playlist_ids": [p.id for p in playlists]
        }

# ==========================================
# ✅ OPTIONS HANDLER (CORS)
# ==========================================

@app.options("/list/{token}.m3u")
@app.options("/list/{token}.m3u8")
@app.options("/p/{token}.m3u")
@app.options("/p/{token}.m3u8")
@app.options("/list/{token}/{playlist_id}.m3u")
@app.options("/list/{token}/{playlist_id}.m3u8")
@app.options("/p/{token}/{playlist_id}.m3u")
@app.options("/p/{token}/{playlist_id}.m3u8")
async def list_options():
    return Response(
        content="",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )

# ==========================================
# 📥 MAIN EXPORT ENDPOINT
# ==========================================

@app.get("/list/{token}/{playlist_id}.m3u")
@app.get("/list/{token}/{playlist_id}.m3u8")
@app.get("/p/{token}/{playlist_id}.m3u")
@app.get("/p/{token}/{playlist_id}.m3u8")
@app.get("/list/{token}.m3u")
@app.get("/list/{token}.m3u8")
@app.get("/p/{token}.m3u")
@app.get("/p/{token}.m3u8")
async def iptv_with_ext(token: str, playlist_id: int = None, db: AsyncSession = Depends(get_db)):
    """Универсальный экспорт с отладкой"""
    print(f"📥 Запрос плейлиста: token={token}, playlist_id={playlist_id}")
    
    async with async_session() as session:
        user = None
        
        # Пробуем найти по короткому токену
        if len(token) >= 6 and len(token) <= 20 and token.replace('_', '').replace('-', '').isalnum():
            result = await session.execute(select(User).where(User.playlist_token == token))
            user = result.scalar_one_or_none()
            if user:
                print(f"✅ Найдено пользователя: {user.email}")
            else:
                print(f"❌ Пользователь с токеном '{token}' не найден!")
        
        # Пробуем декодировать base64
        if not user:
            try:
                clean_token = unquote(token)
                missing_padding = len(clean_token) % 4
                if missing_padding:
                    clean_token += '=' * (4 - missing_padding)
                decoded = base64.urlsafe_b64decode(clean_token.encode()).decode()
                email = decoded.split(":")[0]
                print(f"🔍 Декодирован base64 токен: email={email}")
                
                result = await session.execute(select(User).where(User.email == email))
                user = result.scalar_one_or_none()
            except Exception as e:
                print(f"⚠️ Token decode failed: {e}")
        
        if not user:
            print(f"❌ 404: Пользователь не найден")
            raise HTTPException(status_code=404, detail="Playlist not found - user not found")
        
        # Берём первый плейлист
        if playlist_id:
            try:
                result = await session.execute(
                    select(Playlist).where(
                        Playlist.id == int(playlist_id),
                        Playlist.owner_email == user.email
                    ).limit(1)
                )
            except:
                result = await session.execute(
                    select(Playlist).where(
                        Playlist.owner_email == user.email
                    ).order_by(Playlist.id).limit(1)
                )
        else:
            result = await session.execute(
                select(Playlist).where(
                    Playlist.owner_email == user.email
                ).order_by(Playlist.id).limit(1)
            )
        
        playlist_obj = result.scalar_one_or_none()
        if not playlist_obj:
            print(f"❌ 404: Нет плейлистов у {user.email}")
            raise HTTPException(status_code=404, detail="No active playlist")
        
        print(f"✅ Плейлист: {playlist_obj.name} (id={playlist_obj.id})")
        
        # Получаем активные каналы
        result = await session.execute(
            select(Channel).where(
                Channel.playlist_id == playlist_obj.id,
                Channel.active == True
            ).order_by(Channel.group_title, Channel.name)
        )
        channels = result.scalars().all()
        
        if not channels:
            print(f"❌ 404: Нет активных каналов в плейлисте")
            raise HTTPException(status_code=404, detail="Playlist is empty")
        
        print(f"✅ Найдено {len(channels)} активных каналов")
        
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
        print(f"✅ Отправляем плейлист размером {len(m3u_content)} байт")
        
        return Response(
            content=m3u_content,
            media_type="audio/x-mpegurl",
            headers={
                "Content-Disposition": f'attachment; filename="playlist.m3u"',
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                "Connection": "keep-alive",
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
