# Этот файл нужен для Railway/Render чтобы найти точку входа
# Он просто импортирует и запускает приложение из app.main

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
