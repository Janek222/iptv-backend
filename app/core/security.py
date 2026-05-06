# app/core/security.py
import os
import random
import string
import httpx
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User
import base64
import secrets

# ==========================================
# НАСТРОЙКИ (из переменных окружения)
# ==========================================
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = "JFork IPTV <onboarding@resend.dev>"

# ==========================================
# ОТПРАВКА EMAIL (через Resend API)
# ==========================================
async def send_verification_email(to_email: str, code: str):
    """Отправляет код подтверждения через Resend API"""
    if not RESEND_API_KEY:
        print(f"⚠️ RESEND_API_KEY не настроен! Код для {to_email}: {code}")
        return False

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "from": RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": "🔐 Ваш код доступа: JFork IPTV",
        "html": f"""
        <html>
          <body style="font-family: Arial, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; margin: 0;">
            <div style="max-width: 400px; margin: 0 auto; background: #1e293b; padding: 30px; border-radius: 12px; text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
              <h2 style="color: #3b82f6; margin-top: 0;">📡 JFork IPTV</h2>
              <p style="color: #94a3b8; font-size: 1rem;">Ваш код для входа:</p>
              <h1 style="font-size: 2.5rem; letter-spacing: 5px; color: #22c55e; background: #0f172a; padding: 15px; border-radius: 8px; margin: 20px 0;">{code}</h1>
              <p style="font-size: 0.9rem; color: #64748b;">Действителен 10 минут</p>
            </div>
          </body>
        </html>
        """
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, headers=headers)
            response.raise_for_status()
        print(f"✅ Письмо с кодом {code} отправлено на {to_email}")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки email: {e}")
        return False

# ==========================================
# ГЕНЕРАЦИЯ И ОТПРАВКА КОДА
# ==========================================
async def generate_and_send_code(email: str, db: AsyncSession):
    """Генерирует код, сохраняет в БД и отправляет"""
    code = ''.join(random.choices(string.digits, k=6))
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(email=email)
        db.add(user)
    
    user.verification_code = code
    user.code_expires_at = expires_at
    
    await db.commit()
    
    success = await send_verification_email(email, code)
    
    if not success:
        raise Exception("Failed to send verification email. Check RESEND_API_KEY.")
    
    return True

# ==========================================
# ПРОВЕРКА КОДА И ВХОД
# ==========================================
async def verify_code_and_login(email: str, code: str, db: AsyncSession) -> str:
    """Проверяет код и возвращает токен"""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user:
        raise Exception("User not found.")
    
    if not user.verification_code or user.verification_code != code:
        raise Exception("Invalid verification code.")
    
    if user.code_expires_at and user.code_expires_at < datetime.utcnow():
        raise Exception("Verification code expired.")
    
    user.verification_code = None
    user.code_expires_at = None
    
    if not user.trial_ends_at:
        user.trial_ends_at = datetime.utcnow() + timedelta(days=3)
        
    await db.commit()
    await db.refresh(user)
    
    random_part = secrets.token_urlsafe(16)
    token_content = f"{email}:{random_part}"
    
    # ✅ Генерируем токен С = (как было изначально)
    token = base64.urlsafe_b64encode(token_content.encode()).decode()
    
    print(f"✅ User {email} logged in successfully")
    return token
