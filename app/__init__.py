# Импортируем Base из базы данных
from app.core.database import Base

# Импортируем модели (они должны быть где-то определены)
# Если у тебя есть файл app/models.py с классами User, Playlist, Channel
# то раскомментируй строку ниже:
# from app.models import User, Playlist, Channel

# Если модели в этом же файле или в других файлах папки models/
# то импортируй их отсюда

# ВРЕМЕННО: создадим пустые заглушки чтобы приложение запустилось
# УДАЛИ ЭТОТ КОГДА ДОБАВИШЬ РЕАЛЬНЫЕ МОДЕЛИ!
from sqlalchemy import Column, Integer, String

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)

class Playlist(Base):
    __tablename__ = "playlists"
    id = Column(Integer, primary_key=True)

class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)

__all__ = ["Base", "User", "Playlist", "Channel"]
