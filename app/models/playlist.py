from sqlalchemy import Column, Integer, String
# ✅ НЕ from app.models import Base, а:
from app.core.database import Base

class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    owner_email = Column(String(255), nullable=False, index=True)