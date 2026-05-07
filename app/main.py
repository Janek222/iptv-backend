@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting JFork IPTV Backend...")
    
    # Инициализируем движок БД
    init_db_engine()
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Tables ready")
    
    yield
    await engine.dispose()
    print("🔌 Database disconnected")
