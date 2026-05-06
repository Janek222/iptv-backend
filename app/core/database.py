import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# ==========================================
# CONFIG
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL not found in environment variables!")

# Async Engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True
    # sslmode уже в DATABASE_URL от Neon, connect_args не нужен
)

# Session Factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Единый Base для ВСЕХ моделей
Base = declarative_base()

# ==========================================
# 🔥 КРИТИЧНО: ИМПОРТЫ МОДЕЛЕЙ СРАЗУ ПОСЛЕ BASE!
# ==========================================
# Это регистрирует модели в Base.metadata ДО любого вызова create_all()
from app.models.user import User          # noqa: F401
from app.models.playlist import Playlist  # noqa: F401
from app.models.channel import Channel    # noqa: F401

# ==========================================
# DEPENDENCY
# ==========================================
async def get_db():
    """Зависимость FastAPI для получения сессии БД"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# ==========================================
# INIT DB
# ==========================================
async def init_db():
    """Создание/обновление схемы БД"""
    # 🔍 Отладка: что видит SQLAlchemy?
    print(f"\n🔍 Tables in metadata: {sorted(Base.metadata.tables.keys())}")
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    print("✅ All tables created")
    print(f"📋 Registered tables: {sorted(Base.metadata.tables.keys())}\n")
