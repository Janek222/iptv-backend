# app/models/channel.py
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from app.core.database import Base

class Channel(Base):
    __tablename__ = "channels"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    group_title = Column(String, default="General")
    tvg_id = Column(String, nullable=True)
    tvg_name = Column(String, nullable=True)
    tvg_logo = Column(String, nullable=True)
    tvg_country = Column(String, nullable=True)
    tvg_language = Column(String, nullable=True)
    channel_number = Column(Integer, nullable=True)
    timeshift = Column(String, nullable=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"), nullable=False)
    
    # 🔥 ОБЯЗАТЕЛЬНО: поле active
    active = Column(Boolean, default=True)