# main.py
import shutil
import os
import sqlite3
import uuid
from config import config

# --- 🔧 1. إصلاح مسار FFmpeg (يجب أن يكون في البداية قبل أي استدعاء آخر) ---
os.environ["PATH"] += os.pathsep + config.FFMPEG_BIN_PATH

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import httpx
import uvicorn

# --- استيراد دوال قاعدة البيانات ---
from database.db_manager import (
    get_all_meetings, add_meeting, get_meeting_by_id, 
    update_meeting_status, delete_meeting_by_id, get_meeting_at,
    suggest_slots, DB_NAME, get_user_role_by_email
)

# --- استيراد دوال جوجل كالندر والشيتات ---
from google_sync.google_calendar import add_event_to_google, delete_event_from_google
from google_sync.google_sheets import sync_sqlite_to_sheets

# --- استيراد دوال البوت والذكاء الاصطناعي ---
from message_router import handle_message 
from utils.transcriber import transcribe_audio_free 

app = FastAPI()

# ✅ إعداد CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ إعداد الملفات الثابتة والقوالب
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# بيانات البوت
TELEGRAM_API_URL = config.TELEGRAM_API_URL

# --- دوال مساعدة ---
async def send_telegram_notification(chat_id, message):
    if not chat_id or chat_id == 0: return 
    async with httpx.AsyncClient() as client:
        try:
            await client.post(TELEGRAM_API_URL, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            })
        except Exception as e:
            print(f"Failed to notify user: {e}")

class TaskObj:
    def __init__(self, **entries):
        self.__dict__.update(entries)
        if 'title' in entries:
            self.task = entries['title']

# ================= ROUTES =================

# 1. الصفحة الرئيسية
@app.get("/", response_class=HTMLResponse)
async def read_tasks(request: Request):
    meetings = get_all_meetings() 
    return templates.TemplateResponse("index.html", {"request": request, "tasks": meetings})

# 2. صفحة الشات الجديدة
@app.get("/chat", response_class=HTMLResponse)
async def chat_interface(request: Request):
    return templates.TemplateResponse("web_chat.html", {"request": request})

# 3. API لاستقبال رسائل الشات من الويب
@app.post("/api/chat")
async def web_chat_api(data: dict):
    user_text = data.get("message", "")
    email = data.get("email", "").strip().lower()
    
    user = get_user_role_by_email(email)
    if not user:
        return {"reply": "🔒 هذا الإيميل غير مسجل. يرجى الاتصال بالأدمن لإضافتك."}
    
    try:
        reply = handle_message(user_text, user_id=0, email=email)
    except TypeError:
        simulated_id = user['telegram_id'] if user['telegram_id'] else 999999
        reply = handle_message(user_text, simulated_id)

    return {"reply": reply}

# 4. API لاستقبال الصوت من الويب
@app.post("/api/voice")
async def web_voice_api(file: UploadFile = File(...), email: str = Form(...)):
    # توليد اسم عشوائي للملف لمنع التداخل (UUID)
    unique_id = uuid.uuid4().hex
    # المتصفح بيرسل WebM غالباً
    temp_filename = f"web_voice_{unique_id}.webm" 
    
    try:
        # حفظ الملف القادم من الويب
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # التأكد من أن الملف تم حفظه وله حجم
        if not os.path.exists(temp_filename) or os.path.getsize(temp_filename) == 0:
            return {"reply": "⚠️ حدث خطأ في استلام الملف الصوتي."}

        # تحويل الصوت لنص
        text = transcribe_audio_free(temp_filename)
        
    except Exception as e:
        print(f"Server Error handling voice: {e}")
        text = None
        
    finally:
        # تنظيف الملف المؤقت
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except:
                pass
        
    if not text:
        return {"message": "", "reply": "⚠️ لم أستطع سماع الصوت بوضوح (حاول مرة أخرى)."}
        
    # تمرير النص الناتج لـ API الشات
    return await web_chat_api({"message": text, "email": email})
# 5. إضافة يدوية من الويب
@app.post("/add_from_web")
async def add_task_web(
    task_name: str = Form(...), 
    task_date: str = Form(...), 
    task_time: str = Form(...),
    task_type: str = Form(...),
    task_location: str = Form(None)
):
    status = "pending" 
    location = task_location if task_type == 'offline' else 'Online Meeting'
    add_meeting(title=task_name, date=task_date, time=task_time, m_type=task_type, location=location, requester_id=0, status=status)
    sync_sqlite_to_sheets()
    return RedirectResponse(url="/", status_code=303)

# 6. الموافقة
@app.get("/approve_meeting")
async def approve_meeting(id: int, force: str = 'false'):
    meeting = get_meeting_by_id(id)
    if not meeting:
        return HTMLResponse("<h1>❌ Error: Meeting not found.</h1>")

    if force == 'true':
        old_meeting = get_meeting_at(meeting['date'], meeting['time'])
        if old_meeting:
            if old_meeting['calendar_id']:
                delete_event_from_google(old_meeting['calendar_id'])
            delete_meeting_by_id(old_meeting['id'])

    task_obj = TaskObj(**meeting)
    cal_id = add_event_to_google(task_obj)

    if cal_id:
        update_meeting_status(id, "confirmed", cal_id)
        sync_sqlite_to_sheets()
        
        msg = (f"✅ **تمت الموافقة على اجتماعك!**\n"
               f"📌 العنوان: {meeting['title']}\n"
               f"📅 الموعد: {meeting['date']} | ⏰ {meeting['time']}")
        await send_telegram_notification(meeting['requester_id'], msg)
        
        return HTMLResponse(f"<h1>✅ Approved!</h1><p>Meeting '{meeting['title']}' is now confirmed.</p>")
    return HTMLResponse("<h1>⚠️ Sync Failed</h1>")

# 7. الرفض
@app.get("/reject_meeting")
async def reject_meeting(id: int):
    meeting = get_meeting_by_id(id)
    if meeting:
        suggestions = suggest_slots(meeting['date'])
        sug_text = "\n".join([f"▫️ {s}" for s in suggestions]) if suggestions else "لا يوجد مواعيد متاحة حالياً."
        
        notif_msg = (f"❌ **عذراً، تم رفض طلب اجتماعك:**\n"
                     f"📌 العنوان: {meeting['title']}\n\n"
                     f"💡 **إليك مواعيد بديلة متاحة:**\n"
                     f"{sug_text}")
        await send_telegram_notification(meeting['requester_id'], notif_msg)

    delete_meeting_by_id(id)
    sync_sqlite_to_sheets()
    return HTMLResponse("<h1>🗑️ Rejected</h1><p>User notified with alternatives.</p>")

# 8. Webhook
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        reply_text = handle_message(text, chat_id)
        await send_telegram_notification(chat_id, reply_text)
    return {"ok": True}

@app.post("/api/login")
async def api_login_check(data: dict):
    email = data.get("email", "").strip().lower()
    
    # البحث في الداتا بيز
    user = get_user_role_by_email(email)
    
    if user:
        return JSONResponse({
            "success": True, 
            "name": user['name'], 
            "role": user['role']
        })
    else:
        # لو غير موجود نرجع 401 Unauthorized
        return JSONResponse({
            "success": False, 
            "message": "❌ هذا الإيميل غير مسجل في النظام."
        }, status_code=401)

if __name__ == "__main__":
    # التأكد من وجود المجلدات
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    
    print("🚀 Server is running. Press Ctrl+C to stop.")
    
    try:
        # تشغيل السيرفر داخل بلوك try لتجاهل أخطاء الإغلاق اليدوي
        uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=config.DEBUG)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user (Graceful Shutdown).")
    except Exception as e:
        print(f"⚠️ Unexpected Error: {e}")