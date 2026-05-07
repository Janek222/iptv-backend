# main.py - Entry point for Railway/Render
# Этот файл просто запускает приложение из app.main

import os
import sys

if __name__ == "__main__":
    # Добавляем текущую директорию в путь
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Импортируем uvicorn ВНУТРИ __main__ (не при импорте!)
    import uvicorn
    
    # Запускаем приложение из app.main:app
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
