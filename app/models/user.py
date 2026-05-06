from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
import uuid
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    
    # 🔑 ТОКЕН ДЛЯ ПРЯМЫХ ССЫЛОК НА ПЛЕЙЛИСТ (как у konkurentov)
    playlist_token = Column(String(20), unique=True, nullable=True, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<User(email='{self.email}', token='{self.playlist_token}')>"