# ✅ ПРАВИЛЬНЫЙ ИМПОРТ - ТОЛЬКО Base из database
from app.core.database import Base

# 📦 Остальные импорты для моделей
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

# 👤 User модель
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    playlist_token = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    playlists = relationship("Playlist", back_populates="owner", cascade="all, delete-orphan")

# 📺 Playlist модель
class Playlist(Base):
    __tablename__ = "playlists"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    owner_email = Column(String, ForeignKey("users.email"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    owner = relationship("User", back_populates="playlists")
    channels = relationship("Channel", back_populates="playlist", cascade="all, delete-orphan")

# 📡 Channel модель
class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    url = Column(Text, nullable=False)
    group_title = Column(String, nullable=True)
    tvg_name = Column(String, nullable=True)
    tvg_logo = Column(String, nullable=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"), nullable=False)
    active = Column(Boolean, default=True)
    playlist = relationship("Playlist", back_populates="channels")

# ✅ Экспорт
__all__ = ["Base", "User", "Playlist", "Channel"]
