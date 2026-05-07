# ✅ ПРАВИЛЬНО - подключение создаётся только при первом использовании
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DATABASE_URL = os.getenv("DATABASE_URL")

# Создаём engine, но НЕ подключаемся сразу
engine = create_async_engine(DATABASE_URL, echo=False) if DATABASE_URL else None

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False) if engine else None
Base = declarative_base()

# Функция для получения сессии - вызывается только при запросе
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
