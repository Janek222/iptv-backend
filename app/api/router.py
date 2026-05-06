from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sql_delete, update as sql_update
from app.core.database import get_db
from app.core.security import generate_and_send_code, verify_code_and_login
from app.models import User, Playlist, Channel
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime, timedelta
import base64
import httpx
import secrets
import string
import traceback
import os  # ✅ ДОБАВЛЕНО: без этого не работал os.getenv

router = APIRouter()

# ==========================================
# 🔑 УТИЛИТА: ГЕНЕРАЦИЯ ТОКЕНА
# ==========================================
def generate_playlist_token(length: int = 10) -> str:
    chars = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

# ==========================================
# OPTIONS HANDLER ДЛЯ IPTV ПЛЕЕРОВ
# ==========================================
@router.options("/list/{token}.m3u")
@router.options("/list/{token}.m3u8")
@router.options("/p/{token}.m3u")
@router.options("/p/{token}.m3u8")
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
# PYDANTIC MODELS
# ==========================================
class EmailRequest(BaseModel):
    email: EmailStr

class VerifyRequest(BaseModel):
    email: EmailStr
    code: str

class PlaylistCreate(BaseModel):
    name: str

class ChannelCreate(BaseModel):
    name: str
    url: str
    group_title: Optional[str] = "General"
    tvg_id: Optional[str] = None
    tvg_name: Optional[str] = None
    tvg_logo: Optional[str] = None
    tvg_country: Optional[str] = None
    tvg_language: Optional[str] = None
    channel_number: Optional[int] = None
    timeshift: Optional[str] = None
    active: Optional[bool] = True

class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    group_title: Optional[str] = None
    tvg_id: Optional[str] = None
    tvg_name: Optional[str] = None
    tvg_logo: Optional[str] = None
    tvg_country: Optional[str] = None
    tvg_language: Optional[str] = None
    channel_number: Optional[int] = None
    timeshift: Optional[str] = None
    active: Optional[bool] = None

class PlaylistImportURL(BaseModel):
    url: str
    playlist_id: Optional[int] = None
    name: Optional[str] = None

class PlaylistImportText(BaseModel):
    content: str
    playlist_id: Optional[int] = None
    name: Optional[str] = None

class ChannelBulkUpdate(BaseModel):
    channel_ids: List[int]
    active: bool

# ==========================================
# AUTH ENDPOINTS
# ==========================================
@router.post("/auth/request-code")
async def request_code(data: EmailRequest, db: AsyncSession = Depends(get_db)):
    try:
        await generate_and_send_code(data.email, db)
        return {"message": "Code sent", "email": data.email}
    except Exception as e:
        print(f"❌ Request code error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auth/verify")
async def verify_login(data: VerifyRequest, db: AsyncSession = Depends(get_db)):
    try:
        token = await verify_code_and_login(data.email, data.code, db)
        return {"token": token, "message": "Logged in successfully"}
    except Exception as e:
        print(f"❌ Verify login error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=401, detail=str(e))

# ==========================================
# DEPENDENCIES
# ==========================================
async def get_current_user(authorization: str = Header(...), db: AsyncSession = Depends(get_db)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")
    
    token = authorization.split(" ")[1]
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        email = decoded.split(":")[0]
    except Exception as e:
        print(f"❌ Token decode error: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# ==========================================
# 🎯 НОВЫЙ ENDPOINT: ПОЛУЧИТЬ ПРЯМУЮ ССЫЛКУ
# ==========================================
@router.get("/playlists/{playlist_id}/get-direct-link")
async def get_direct_playlist_link(
    playlist_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Генерирует/возвращает прямую ссылку на плейлист:
    → /list/abc123def4.m3u
    """
    # Проверяем доступ к плейлисту
    result = await db.execute(select(Playlist).where(
        Playlist.id == playlist_id,
        Playlist.owner_email == user.email
    ))
    playlist = result.scalar_one_or_none()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Если у пользователя нет токена — генерируем
    if not user.playlist_token:
        # Проверяем уникальность
        while True:
            new_token = generate_playlist_token()
            result = await db.execute(select(User).where(User.playlist_token == new_token))
            if not result.scalar_one_or_none():
                user.playlist_token = new_token
                await db.commit()
                break
    
    # Формируем ссылки
    base_url = os.getenv("BASE_URL", "https://your-domain.com")
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
# 🔄 ОБНОВИТЬ/СГЕНЕРИРОВАТЬ ТОКЕН ВРУЧНУЮ
# ==========================================
@router.post("/user/regenerate-playlist-token")
async def regenerate_playlist_token(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Принудительная перегенерация токена (если скомпрометирован)"""
    while True:
        new_token = generate_playlist_token()
        result = await db.execute(select(User).where(User.playlist_token == new_token))
        if not result.scalar_one_or_none():
            user.playlist_token = new_token
            await db.commit()
            break
    
    base_url = os.getenv("BASE_URL", "https://your-domain.com")
    return {
        "message": "Token regenerated",
        "new_token": user.playlist_token,
        "direct_link": f"{base_url}/list/{user.playlist_token}.m3u"
    }

# ==========================================
# EXPORT ENDPOINTS (СТАРЫЕ — для кнопки "Скачать")
# ==========================================
@router.get("/playlists/{playlist_id}/export")
async def export_playlist_endpoint(
    playlist_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Экспорт плейлиста (для кнопки скачать)"""
    try:
        result = await db.execute(select(Playlist).where(
            Playlist.id == playlist_id,
            Playlist.owner_email == user.email
        ))
        playlist = result.scalar_one_or_none()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        result = await db.execute(select(Channel).where(
            Channel.playlist_id == playlist_id,
            Channel.active == True
        ))
        channels = result.scalars().all()
        
        m3u_content = "#EXTM3U\n"
        for ch in channels:
            logo = ch.tvg_logo or ""
            group = ch.group_title or "General"
            tvg_id = ch.tvg_id or ""
            tvg_name = ch.tvg_name or ch.name
            
            m3u_content += f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{tvg_name}" tvg-logo="{logo}" group-title="{group}",{ch.name}\n'
            m3u_content += f'{ch.url}\n'
        
        return PlainTextResponse(
            content=m3u_content,
            media_type="audio/x-mpegurl",
            headers={
                "Content-Disposition": f"attachment; filename={playlist.name}.m3u"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Export playlist error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 🎯 ЗАЩИЩЁННЫЙ ЭКСПОРТ ПО КОРОТКОМУ ТОКЕНУ
# ==========================================
@router.get("/list/{token}.m3u")
@router.get("/list/{token}.m3u8")
@router.get("/p/{token}.m3u")
@router.get("/p/{token}.m3u8")
async def export_playlist_protected(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    ЗАЩИЩЕННЫЙ экспорт — короткий токен в пути URL.
    Работает в ЛЮБЫХ IPTV плеерах!
    Формат: /list/abc123def4.m3u
    """
    try:
        if not token or len(token) < 6:
            raise HTTPException(status_code=404, detail="Invalid token")
        
        # 🔍 Ищем пользователя по короткому токену
        result = await db.execute(select(User).where(User.playlist_token == token))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        # 📋 Берём первый активный плейлист
        result = await db.execute(
            select(Playlist).where(
                Playlist.owner_email == user.email,
                Playlist.is_active == True
            ).order_by(Playlist.id).limit(1)
        )
        playlist = result.scalar_one_or_none()
        if not playlist:
            raise HTTPException(status_code=404, detail="No active playlist")
        
        # 📺 Получаем каналы
        result = await db.execute(
            select(Channel).where(
                Channel.playlist_id == playlist.id,
                Channel.active == True
            ).order_by(Channel.channel_number.nullsfirst())
        )
        channels = result.scalars().all()
        
        if not channels:
            raise HTTPException(status_code=404, detail="Playlist is empty")
        
        # 🧾 Формируем M3U
        m3u_content = "#EXTM3U\n"
        for ch in channels:
            logo = ch.tvg_logo or ""
            group = ch.group_title or "General"
            tvg_id = ch.tvg_id or ""
            tvg_name = ch.tvg_name or ch.name
            
            m3u_content += f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{tvg_name}" tvg-logo="{logo}" group-title="{group}",{ch.name}\n'
            m3u_content += f'{ch.url}\n'
        
        # 🎯 Правильный Content-Type для IPTV
        media_type = "application/vnd.apple.mpegurl"
        
        return Response(
            content=m3u_content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="{user.email}.m3u"',
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                "Cache-Control": "public, max-age=300",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Export protected playlist error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# PLAYLIST ENDPOINTS
# ==========================================
@router.get("/playlists")
async def get_playlists(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Playlist).where(Playlist.owner_email == user.email))
        playlists = result.scalars().all()
        
        playlists_with_count = []
        for pl in playlists:
            result = await db.execute(select(Channel).where(
                Channel.playlist_id == pl.id
            ))
            channels_count = result.scalars().all()
            active_count = len([ch for ch in channels_count if ch.active])
            total_count = len(channels_count)
            
            playlists_with_count.append({
                "id": pl.id,
                "name": pl.name,
                "active_channels": active_count,
                "total_channels": total_count
            })
        
        return playlists_with_count
    except Exception as e:
        print(f"❌ Get playlists error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/playlists")
async def create_playlist(data: PlaylistCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        playlist = Playlist(name=data.name, owner_email=user.email)
        db.add(playlist)
        await db.commit()
        await db.refresh(playlist)
        return {"id": playlist.id, "name": playlist.name}
    except Exception as e:
        print(f"❌ Create playlist error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/playlists/{playlist_id}")
async def delete_playlist(playlist_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Playlist).where(
            Playlist.id == playlist_id, 
            Playlist.owner_email == user.email
        ))
        playlist = result.scalar_one_or_none()
        if playlist:
            await db.delete(playlist)
            await db.commit()
        return {"message": "Deleted"}
    except Exception as e:
        print(f"❌ Delete playlist error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# CHANNEL ENDPOINTS
# ==========================================
@router.get("/playlists/{playlist_id}/channels")
async def get_channels(playlist_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Channel).where(Channel.playlist_id == playlist_id))
        channels = result.scalars().all()
        
        return [
            {
                "id": ch.id,
                "name": ch.name,
                "url": ch.url,
                "group_title": ch.group_title or "General",
                "tvg_id": ch.tvg_id,
                "tvg_name": ch.tvg_name,
                "tvg_logo": ch.tvg_logo,
                "tvg_country": ch.tvg_country,
                "tvg_language": ch.tvg_language,
                "channel_number": ch.channel_number,
                "timeshift": ch.timeshift,
                "active": ch.active,
                "playlist_id": ch.playlist_id
            }
            for ch in channels
        ]
    except Exception as e:
        print(f"❌ Get channels error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/playlists/{playlist_id}/channels")
async def add_channel(playlist_id: int, data: ChannelCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Playlist).where(
            Playlist.id == playlist_id, 
            Playlist.owner_email == user.email
        ))
        playlist = result.scalar_one_or_none()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        channel = Channel(
            name=data.name,
            url=data.url,
            group_title=data.group_title,
            tvg_id=data.tvg_id,
            tvg_name=data.tvg_name,
            tvg_logo=data.tvg_logo,
            tvg_country=data.tvg_country,
            tvg_language=data.tvg_language,
            channel_number=data.channel_number,
            timeshift=data.timeshift,
            active=data.active if data.active is not None else True,
            playlist_id=playlist.id
        )
        db.add(channel)
        await db.commit()
        await db.refresh(channel)
        return channel
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Add channel error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/playlists/{playlist_id}/channels/{channel_id}")
async def update_channel(playlist_id: int, channel_id: int, data: ChannelUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Playlist).where(
            Playlist.id == playlist_id, 
            Playlist.owner_email == user.email
        ))
        playlist = result.scalar_one_or_none()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        result = await db.execute(select(Channel).where(
            Channel.id == channel_id, 
            Channel.playlist_id == playlist_id
        ))
        channel = result.scalar_one_or_none()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(channel, field, value)
        
        await db.commit()
        await db.refresh(channel)
        return channel
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Update channel error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/playlists/{playlist_id}/channels/{channel_id}")
async def delete_channel(playlist_id: int, channel_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Playlist).where(
            Playlist.id == playlist_id, 
            Playlist.owner_email == user.email
        ))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        result = await db.execute(select(Channel).where(
            Channel.id == channel_id, 
            Channel.playlist_id == playlist_id
        ))
        channel = result.scalar_one_or_none()
        if channel:
            await db.delete(channel)
            await db.commit()
        return {"message": "Deleted"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Delete channel error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# TOGGLE CHANNEL
# ==========================================
@router.patch("/playlists/{playlist_id}/channels/{channel_id}/toggle")
async def toggle_channel(
    playlist_id: int,
    channel_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await db.execute(select(Playlist).where(
            Playlist.id == playlist_id,
            Playlist.owner_email == user.email
        ))
        playlist = result.scalar_one_or_none()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        result = await db.execute(select(Channel).where(
            Channel.id == channel_id,
            Channel.playlist_id == playlist_id
        ))
        channel = result.scalar_one_or_none()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        
        channel.active = not channel.active
        await db.commit()
        await db.refresh(channel)
        
        return {
            "id": channel.id,
            "name": channel.name,
            "active": channel.active,
            "message": "Channel activated" if channel.active else "Channel deactivated"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Toggle channel error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# BULK OPERATIONS
# ==========================================
@router.post("/playlists/{playlist_id}/channels/bulk-update")
async def bulk_update_channels(
    playlist_id: int,
    data: ChannelBulkUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await db.execute(select(Playlist).where(
            Playlist.id == playlist_id, 
            Playlist.owner_email == user.email
        ))
        playlist = result.scalar_one_or_none()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        for channel_id in data.channel_ids:
            result = await db.execute(select(Channel).where(
                Channel.id == channel_id,
                Channel.playlist_id == playlist_id
            ))
            channel = result.scalar_one_or_none()
            if channel:
                channel.active = data.active
        
        await db.commit()
        return {"message": f"Updated {len(data.channel_ids)} channels", "active": data.active}
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Bulk update error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# GROUP ENDPOINTS
# ==========================================
@router.get("/playlists/{playlist_id}/groups")
async def get_groups(playlist_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Playlist).where(
            Playlist.id == playlist_id, 
            Playlist.owner_email == user.email
        ))
        playlist = result.scalar_one_or_none()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        result = await db.execute(select(Channel).where(Channel.playlist_id == playlist_id))
        channels = result.scalars().all()
        
        groups = {}
        for ch in channels:
            group = ch.group_title or "General"
            if group not in groups:
                groups[group] = {"total": 0, "active": 0, "channels": []}
            groups[group]["total"] += 1
            if ch.active:
                groups[group]["active"] += 1
            groups[group]["channels"].append({
                "id": ch.id,
                "name": ch.name,
                "active": ch.active
            })
        
        return groups
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Get groups error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/playlists/{playlist_id}/groups/{group_name}")
async def delete_group(playlist_id: int, group_name: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Playlist).where(
            Playlist.id == playlist_id, 
            Playlist.owner_email == user.email
        ))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        await db.execute(sql_delete(Channel).where(
            Channel.playlist_id == playlist_id,
            Channel.group_title == group_name
        ))
        await db.commit()
        return {"message": f"Deleted group {group_name}"}
    except Exception as e:
        print(f"❌ Delete group error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/playlists/{playlist_id}/groups/{group_name}/activate")
async def activate_group(playlist_id: int, group_name: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Playlist).where(
            Playlist.id == playlist_id, 
            Playlist.owner_email == user.email
        ))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        await db.execute(
            sql_update(Channel).where(
                Channel.playlist_id == playlist_id,
                Channel.group_title == group_name
            ).values(active=True)
        )
        await db.commit()
        return {"message": f"Activated group {group_name}"}
    except Exception as e:
        print(f"❌ Activate group error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/playlists/{playlist_id}/groups/{group_name}/deactivate")
async def deactivate_group(playlist_id: int, group_name: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Playlist).where(
            Playlist.id == playlist_id, 
            Playlist.owner_email == user.email
        ))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        await db.execute(
            sql_update(Channel).where(
                Channel.playlist_id == playlist_id,
                Channel.group_title == group_name
            ).values(active=False)
        )
        await db.commit()
        return {"message": f"Deactivated group {group_name}"}
    except Exception as e:
        print(f"❌ Deactivate group error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# TOGGLE GROUP
# ==========================================
@router.patch("/playlists/{playlist_id}/groups/{group_name}")
async def update_group_active(
    playlist_id: int,
    group_name: str,
    active: bool = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await db.execute(select(Playlist).where(
            Playlist.id == playlist_id,
            Playlist.owner_email == user.email
        ))
        playlist = result.scalar_one_or_none()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        if group_name == "All" or group_name == "Все":
            stmt = sql_update(Channel).where(
                Channel.playlist_id == playlist_id
            ).values(active=active)
        else:
            stmt = sql_update(Channel).where(
                Channel.playlist_id == playlist_id,
                Channel.group_title == group_name
            ).values(active=active)

        await db.execute(stmt)
        await db.commit()
        
        print(f"✅ Group '{group_name}' set active={active}")
        return {"message": "Success", "active": active}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Toggle group error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# M3U PARSER
# ==========================================
def parse_m3u(content: str) -> list:
    if not content or not content.strip():
        print("⚠️ Empty M3U content")
        return []
    
    channels = []
    try:
        lines = content.strip().split('\n')
    except Exception as e:
        print(f"❌ Error splitting content: {e}")
        return []
    
    current = {
        "name": "", 
        "url": "", 
        "group": "General", 
        "tvg_logo": "", 
        "tvg_id": "", 
        "tvg_name": ""
    }
    pending_group = "General"
    
    for line_num, line in enumerate(lines, 1):
        try:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('#EXTGRP:'):
                group = line[8:].strip()
                if group:
                    if not current["name"]:
                        pending_group = group
                    else:
                        current["group"] = group
                continue
                
            if line.startswith('#EXTINF:'):
                if pending_group != "General":
                    current["group"] = pending_group
                    pending_group = "General"
                    
                if 'tvg-name="' in line:
                    try:
                        start = line.find('tvg-name="') + 10
                        end = line.find('"', start)
                        if start > 9 and end > start:
                            current["tvg_name"] = line[start:end]
                    except:
                        pass
                        
                if 'group-title="' in line:
                    try:
                        start = line.find('group-title="') + 13
                        end = line.find('"', start)
                        if start > 12 and end > start:
                            current["group"] = line[start:end]
                    except:
                        pass
                        
                if 'tvg-logo="' in line:
                    try:
                        start = line.find('tvg-logo="') + 10
                        end = line.find('"', start)
                        if start > 9 and end > start:
                            current["tvg_logo"] = line[start:end]
                    except:
                        pass
                        
                if 'tvg-id="' in line:
                    try:
                        start = line.find('tvg-id="') + 8
                        end = line.find('"', start)
                        if start > 7 and end > start:
                            current["tvg_id"] = line[start:end]
                    except:
                        pass
                        
                if ',' in line:
                    try:
                        current["name"] = line.split(',')[-1].strip().strip('"\' ')
                    except:
                        pass
                        
            elif line.startswith('http://') or line.startswith('https://'):
                current["url"] = line
                if current["name"]:
                    channels.append(current.copy())
                    print(f"✅ Parsed channel: {current['name']}")
                current = {
                    "name": "", 
                    "url": "", 
                    "group": "General", 
                    "tvg_logo": "", 
                    "tvg_id": "", 
                    "tvg_name": ""
                }
        except Exception as e:
            print(f"⚠️ Error parsing line {line_num}: {e}")
            continue
    
    print(f"📺 Total channels parsed: {len(channels)}")
    return channels

# ==========================================
# IMPORT ENDPOINTS
# ==========================================
@router.post("/playlists/import/url")
async def import_from_url(data: PlaylistImportURL, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        print(f"📥 Importing from URL: {data.url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(data.url)
            resp.raise_for_status()
        
        channels = parse_m3u(resp.text)
        
        if not channels:
            raise HTTPException(status_code=400, detail="No channels found in M3U")
        
        if data.playlist_id:
            pl = await db.get(Playlist, data.playlist_id)
            if not pl:
                raise HTTPException(status_code=404, detail="Playlist not found")
        else:
            pl = Playlist(name=data.name or "Imported", owner_email=user.email)
            db.add(pl)
            await db.commit()
            await db.refresh(pl)
        
        for ch in channels:
            db.add(Channel(
                name=ch["name"],
                url=ch["url"],
                group_title=ch["group"],
                tvg_logo=ch["tvg_logo"],
                tvg_id=ch["tvg_id"],
                tvg_name=ch["tvg_name"],
                active=True,
                playlist_id=pl.id
            ))
        
        await db.commit()
        
        return {
            "message": f"Imported {len(channels)} channels",
            "playlist_id": pl.id,
            "playlist_name": pl.name,
            "channels_count": len(channels)
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Import from URL error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Import error: {str(e)}")

@router.post("/playlists/import/text")
async def import_from_text(data: PlaylistImportText, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        print(f"📥 Importing from text, length: {len(data.content)}")
        
        if not data.content or not data.content.strip():
            raise HTTPException(status_code=400, detail="Empty content")
        
        channels = parse_m3u(data.content)
        
        if not channels:
            raise HTTPException(status_code=400, detail="No channels found in M3U. Check your content format.")
        
        if data.playlist_id:
            pl = await db.get(Playlist, data.playlist_id)
            if not pl:
                raise HTTPException(status_code=404, detail="Playlist not found")
        else:
            pl = Playlist(name=data.name or "Imported", owner_email=user.email)
            db.add(pl)
            await db.commit()
            await db.refresh(pl)
        
        for ch in channels:
            db.add(Channel(
                name=ch["name"],
                url=ch["url"],
                group_title=ch["group"],
                tvg_logo=ch.get("tvg_logo", ""),
                tvg_id=ch.get("tvg_id", ""),
                tvg_name=ch.get("tvg_name", ""),
                active=True,
                playlist_id=pl.id
            ))
        
        await db.commit()
        
        return {
            "message": f"Imported {len(channels)} channels",
            "playlist_id": pl.id,
            "playlist_name": pl.name,
            "channels_count": len(channels)
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Import from text error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Import error: {str(e)}")
