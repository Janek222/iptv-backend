from fastapi import APIRouter, Response
from sqlalchemy import select
from app.core.database import get_db
from app.models import User, Playlist, Channel
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import unquote
import base64

router = APIRouter()

@router.get("/iptv/{token}/{filename}")
@router.get("/iptv/{token}/{filename}.m3u")
@router.get("/iptv/{token}/{filename}.m3u8")
async def get_iptv_playlist(token: str, filename: str):
    """Альтернативный endpoint для IPTV через /api/v1/"""
    token = unquote(token)
    filename = unquote(filename)
    
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        email = decoded.split(":")[0]
    except:
        return Response(content="#EXTM3U\n", media_type="audio/x-mpegurl")
    
    async with AsyncSession(get_db()) as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            return Response(content="#EXTM3U\n", media_type="audio/x-mpegurl")
        
        playlist_id_str = filename.replace(".m3u", "").replace(".m3u8", "")
        try:
            playlist_id = int(playlist_id_str)
        except:
            return Response(content="#EXTM3U\n", media_type="audio/x-mpegurl")
        
        result = await session.execute(select(Playlist).where(
            Playlist.id == playlist_id,
            Playlist.owner_email == user.email
        ))
        playlist = result.scalar_one_or_none()
        if not playlist:
            return Response(content="#EXTM3U\n", media_type="audio/x-mpegurl")
        
        result = await session.execute(select(Channel).where(
            Channel.playlist_id == playlist_id,
            Channel.active == True
        ))
        channels = result.scalars().all()
        
        m3u_content = "#EXTM3U\n"
        for ch in channels:
            m3u_content += f'#EXTINF:-1 group-title="{ch.group_title or "General"}",{ch.name}\n'
            m3u_content += f'{ch.url}\n'
        
        return Response(
            content=m3u_content,
            media_type="audio/x-mpegurl",
            headers={"Content-Disposition": f"attachment; filename={playlist.name}.m3u"}
        )