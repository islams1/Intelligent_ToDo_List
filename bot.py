import logging
import os
import sqlite3
import pytz
from datetime import datetime, timedelta
from config import config

# --- 1. إصلاح مسار FFmpeg فوراً قبل استدعاء مكتبات الصوت ---
os.environ["PATH"] += os.pathsep + config.FFMPEG_BIN_PATH

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    filters, ConversationHandler, ContextTypes, CallbackQueryHandler
)

# --- استيرادات المشروع الأصلية ---
from database.db_manager import (
    add_meeting, get_meetings_in_range, get_meeting_at, 
    delete_meeting_by_id, suggest_slots, get_meeting_by_id,
    update_meeting_status, get_all_meetings,
    login_user, get_user_role, logout_user, DB_NAME 
)
from google_sync.google_calendar import add_event_to_google, delete_event_from_google
from utils.email_sender import send_approval_email
from google_sync.google_sheets import sync_sqlite_to_sheets
from message_router import handle_message 
from utils.transcriber import transcribe_audio_free 

# --- 2. إعدادات التوقيت واللوجر (الإضافات الجديدة) ---
CAIRO_TZ = pytz.timezone(config.TIMEZONE)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("system_logs.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SmartBot")

def get_now():
    """جلب الوقت الحالي بتوقيت القاهرة"""
    return datetime.now(CAIRO_TZ)

# --- إعدادات البوت ---
TOKEN = config.TELEGRAM_BOT_TOKEN

# تعريف مراحل المحادثة
LOGIN, CHOOSING, ADD_NAME, ADD_DATE, ADD_TIME, ADD_TYPE, ADD_LOCATION, CONFIRM_CONFLICT, DELETE_NAME, VIEW_OPTIONS = range(10)

# --- كلاس مساعد ---
class TaskObj:
    def __init__(self, **entries):
        self.__dict__.update(entries)
        if 'title' in entries: self.task = entries['title']

# --- 3. نظام التذكير الآلي (Task 2) ---
async def reminder_check_callback(context: ContextTypes.DEFAULT_TYPE):
    """فحص الاجتماعات المؤكدة وإرسال تذكير قبل 30 دقيقة"""
    now = get_now()
    # تحديد نافذة زمنية (بعد 25 إلى 35 دقيقة من الآن)
    rem_start = (now + timedelta(minutes=25)).strftime("%H:%M")
    rem_end = (now + timedelta(minutes=35)).strftime("%H:%M")
    today_str = now.strftime("%Y-%m-%d")

    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        # جلب الاجتماعات التي لم يرسل لها تذكير وحالتها مؤكدة وموعدها اقترب
        c.execute('''
            SELECT * FROM meetings 
            WHERE date = ? AND status = 'confirmed' AND reminder_sent = 0
            AND time >= ? AND time <= ?
        ''', (today_str, rem_start, rem_end))
        
        upcoming = c.fetchall()
        for meeting in upcoming:
            try:
                msg = (f"⏰ **Meeting Reminder!**\n\n"
                       f"📌 Title: {meeting['title']}\n"
                       f"🕒 Time: {meeting['time']} (Starts in ~30 mins)\n"
                       f"📍 Location: {meeting['location']}")
                
                await context.bot.send_message(chat_id=meeting['requester_id'], text=msg, parse_mode='Markdown')
                c.execute("UPDATE meetings SET reminder_sent = 1 WHERE id = ?", (meeting['id'],))
                logger.info(f"✅ Reminder sent for meeting ID: {meeting['id']}")
            except Exception as e:
                logger.error(f"Failed to send reminder to {meeting['requester_id']}: {e}")
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error in reminder job: {e}")

# --- دوال مساعدة (الأصلية) ---
def format_date_input(date_str):
    for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return date_str

def track(update_or_msg, context):
    if 'old_messages' not in context.user_data:
        context.user_data['old_messages'] = []
    msg_id = None
    if hasattr(update_or_msg, 'message_id'):
        msg_id = update_or_msg.message_id
    elif hasattr(update_or_msg, 'message') and update_or_msg.message:
        msg_id = update_or_msg.message.message_id
    if msg_id and msg_id not in context.user_data['old_messages']:
        context.user_data['old_messages'].append(msg_id)

async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if 'old_messages' in context.user_data:
        for msg_id in reversed(context.user_data['old_messages']):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except:
                pass 
        context.user_data['old_messages'] = []

# --- البداية (Start) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await clear_chat(update, context)
    track(update, context)
    
    user_id = update.effective_user.id
    logout_user(user_id)
    
    text = (
        "👋 **Welcome to Smart Meeting Assistant!**\n\n"
        "🔒 **Session Reset.**\n"
        "📧 Please enter your **Email Address** to login:"
    )
    sent_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode='Markdown')
    track(sent_msg, context)
    
    return LOGIN

# --- معالجة تسجيل الدخول ---
async def handle_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(update, context)
    email = update.message.text.strip().lower()
    user_id = update.effective_user.id
    
    login_result = login_user(user_id, email)
    
    if login_result:
        await update.message.reply_text(f"✅ Login Successful!\nWelcome back, **{login_result['name']}**.", parse_mode='Markdown')
        return await show_main_menu(update, context, login_result)
    else:
        sent_msg = await update.message.reply_text("❌ **Access Denied!**\nThis email is not authorized.\nPlease try again.")
        track(sent_msg, context)
        return LOGIN

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data):
    role_icon = "👑" if user_data['role'] == 'admin' else "👤"
    role_display = "Admin" if user_data['role'] == 'admin' else "User"
    
    text = (
        f"🤖 *Smart Meeting Assistant*\n"
        f"Logged in as: {role_icon} {user_data['name']} ({role_display})\n\n"
        "Ready to manage your schedule. Choose an option:"
    )
    
    keyboard = [
        [InlineKeyboardButton("New Meeting ➕", callback_data="add")],
        [InlineKeyboardButton("View Schedule 📅", callback_data="view")],
        [InlineKeyboardButton("Cancel Meeting ❌", callback_data="delete")]
    ]
    
    sent_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    track(sent_msg, context)
    return CHOOSING

# --- خطوات الإضافة (الأصلية) ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sent_msg = await query.message.reply_text("📝 **Meeting Title**:", parse_mode='Markdown')
    track(sent_msg, context)
    return ADD_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(update, context)
    context.user_data['name'] = update.message.text
    sent_msg = await update.message.reply_text("📅 **Date** (YYYY-MM-DD):", parse_mode='Markdown')
    track(sent_msg, context)
    return ADD_DATE

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(update, context)
    raw_date = update.message.text
    context.user_data['date'] = format_date_input(raw_date)
    sent_msg = await update.message.reply_text("⏰ **Time** (HH:MM) - 24h format:", parse_mode='Markdown')
    track(sent_msg, context)
    return ADD_TIME

async def get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(update, context)
    context.user_data['time'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("🌐 Online", callback_data="online")],
        [InlineKeyboardButton("🏢 Offline", callback_data="offline")]
    ]
    sent_msg = await update.message.reply_text("📍 **Meeting Type?**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    track(sent_msg, context)
    return ADD_TYPE

async def get_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    m_type = query.data
    context.user_data['type'] = m_type
    
    if m_type == 'offline':
        sent_msg = await query.message.reply_text("📍 **Please enter the location:**", parse_mode='Markdown')
        track(sent_msg, context)
        return ADD_LOCATION
    else:
        context.user_data['location'] = "Google Meet (Online)"
        return await finalize_booking(update, context)

async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(update, context)
    context.user_data['location'] = update.message.text
    return await finalize_booking(update, context)

# --- منطق الحجز والتعارض ---
async def finalize_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = context.user_data
    
    user_info = get_user_role(user_id)
    is_admin = (user_info['role'] == 'admin') if user_info else False
    
    existing_meeting = get_meeting_at(data['date'], data['time'])
    
    if existing_meeting:
        if is_admin:
            text = f"⚠️ **Conflict Detected!**\nWith: '{existing_meeting[1]}'. Override?"
            keyboard = [
                [InlineKeyboardButton("⚠️ Override", callback_data="force_add")],
                [InlineKeyboardButton("Cancel", callback_data="cancel_add")]
            ]
        else:
            suggestions = suggest_slots(data['date'])
            sug_text = "\n".join(suggestions) if suggestions else "No nearby slots."
            text = f"❌ **Slot Booked!**\nSuggestions:\n{sug_text}\n\nRequest anyway?"
            keyboard = [
                [InlineKeyboardButton("📩 Request", callback_data="request_anyway")],
                [InlineKeyboardButton("Cancel", callback_data="cancel_add")]
            ]
        sent_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id, text=text, 
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
        )
        track(sent_msg, context)
        return CONFIRM_CONFLICT
    
    return await process_request(update, context, is_conflict=False)

async def handle_conflict_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data
    
    if choice == "cancel_add":
        await query.message.reply_text("❌ Cancelled.")
        return CHOOSING
    if choice == "force_add": 
        return await process_request(update, context, is_conflict=True, force_admin=True)
    if choice == "request_anyway": 
        return await process_request(update, context, is_conflict=True, force_admin=False)

# --- المعالجة النهائية (Dual Sync Integration) ---
async def process_request(update, context, is_conflict=False, force_admin=False):
    data = context.user_data
    user_id = update.effective_user.id
    
    user_info = get_user_role(user_id)
    if not user_info:
        return LOGIN
        
    is_admin = (user_info['role'] == 'admin')
    created_by_name = user_info['name']

    if is_admin:
        status = "confirmed"
        msg_header = "✅ **Meeting Confirmed!**"
    else:
        status = "pending"
        msg_header = "📨 **Request Sent!**\nWaiting for approval..."

    # في حالة التخطي للأدمن، يتم مسح الموعد القديم من الكالندر والداتا بيز
    if is_admin and is_conflict and force_admin:
         old_meeting = get_meeting_at(data['date'], data['time'])
         if old_meeting:
             cal_id_to_del = old_meeting[12] if isinstance(old_meeting, tuple) else old_meeting.get('calendar_id')
             if cal_id_to_del:
                 delete_event_from_google(cal_id_to_del)
             delete_meeting_by_id(old_meeting[0] if isinstance(old_meeting, tuple) else old_meeting.get('id'))

    task_id = add_meeting(
        data['name'], data['date'], data['time'], data['type'], data['location'],
        "N/A", "Medium", user_id, created_by_name, status
    )
    
    if is_admin:
        task_obj = TaskObj(
            task=data['name'], date=data['date'], time=data['time'],
            type=data['type'], location=data['location'], created_by=created_by_name
        )
        cal_id = add_event_to_google(task_obj)
        update_meeting_status(task_id, "confirmed", cal_id)
        final_msg = f"{msg_header}\n👤 Owner: {created_by_name}\n✅ Synced to Calendar & Sheets."
    else:
        email_data = {
            'title': data['name'], 'date': data['date'], 'time': data['time'],
            'type': data['type'], 'location': data['location'],
            'with_whom': "N/A", 'priority': "Medium"
        }
        send_approval_email(task_id, email_data, is_conflict)
        final_msg = f"{msg_header}\n👤 Requester: {created_by_name}"

    sync_sqlite_to_sheets() # مزامنة الشيت دائماً

    if update.callback_query:
        await update.callback_query.message.reply_text(final_msg, parse_mode='Markdown')
    else:
        await update.message.reply_text(final_msg, parse_mode='Markdown')
        
    return CHOOSING

# --- نظام العرض (الأصلي) ---
async def view_tasks_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    today = get_now()
    next_week = today + timedelta(days=7)
    today_str = today.strftime('%Y-%m-%d')
    next_week_str = next_week.strftime('%Y-%m-%d')
    meetings = get_meetings_in_range(today_str, next_week_str)
    msg = f"📅 **Schedule (Next 7 Days):**\nFrom {today_str} to {next_week_str}\n\n"
    msg += format_meetings_list(meetings)
    keyboard = [
        [InlineKeyboardButton("Next 2 Weeks 🗓️", callback_data="view_2weeks")],
        [InlineKeyboardButton("Show Month 📅", callback_data="view_month")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_main")]
    ]
    track(query.message, context)
    await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return VIEW_OPTIONS

async def view_options_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data
    today = get_now()
    today_str = today.strftime('%Y-%m-%d')
    if choice == "back_main":
        user_info = get_user_role(update.effective_user.id)
        return await show_main_menu(update, context, user_info)
    if choice == "view_2weeks":
        end_date = today + timedelta(days=14)
        title = "Upcoming 2 Weeks"
    elif choice == "view_month":
        end_date = today + timedelta(days=30)
        title = "Upcoming Month"
    else: return VIEW_OPTIONS
    end_date_str = end_date.strftime('%Y-%m-%d')
    meetings = get_meetings_in_range(today_str, end_date_str)
    msg = f"📅 **Schedule ({title}):**\nFrom {today_str} to {end_date_str}\n\n"
    msg += format_meetings_list(meetings)
    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_main")]]
    await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return VIEW_OPTIONS

def format_meetings_list(meetings):
    if not meetings: return "📭 No meetings scheduled.\n"
    text = ""
    for m in meetings:
        icon = "✅" if m['status'] == 'confirmed' else "⏳"
        type_icon = "🌐" if m['type'] == 'online' else "🏢"
        text += (
            f"▫️ **{m['title']}** {icon}\n"
            f"   📅 {m['date']} ⏰ {m['time']}\n"
            f"   {type_icon} {m['type'].title()} " + (f"({m['location']})" if m['type']=='offline' else "") + "\n\n"
        )
    return text

# --- الحذف (Dual Sync Integration) ---
async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_info = get_user_role(query.from_user.id)
    if not user_info or user_info['role'] != 'admin':
        await query.message.reply_text("⛔ **Admin Access Only!**")
        return CHOOSING
    sent_msg = await query.message.reply_text("🗑️ Enter Title to delete:", parse_mode='Markdown')
    track(sent_msg, context)
    return DELETE_NAME

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(update, context)
    target_name = update.message.text
    all_meetings = get_all_meetings()
    target_meeting = next((m for m in all_meetings if m['title'].strip().lower() == target_name.strip().lower()), None)
    
    if target_meeting:
        if target_meeting['calendar_id']:
            delete_event_from_google(target_meeting['calendar_id'])
        delete_meeting_by_id(target_meeting['id'])
        sync_sqlite_to_sheets()
        sent_msg = await update.message.reply_text(f"🗑️ Deleted: {target_name}")
    else:
        sent_msg = await update.message.reply_text(f"⚠️ Not found: '{target_name}'")
    track(sent_msg, context)
    return CHOOSING

# --- AI & Voice Handlers ---
async def handle_ai_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(update, context)
    user_id = update.effective_user.id
    if not get_user_role(user_id):
        await update.message.reply_text("🔒 Please login first.")
        return LOGIN
    reply_text = handle_message(update.message.text, user_id) 
    sent_msg = await update.message.reply_text(reply_text, parse_mode='Markdown')
    track(sent_msg, context)
    return CHOOSING

async def handle_voice_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track(update, context)
    user_id = update.effective_user.id
    if not get_user_role(user_id):
        await update.message.reply_text("🔒 Please login first.")
        return LOGIN
    status_msg = await update.message.reply_text("🎧 جارٍ الاستماع (Google Free)...")
    try:
        new_file = await context.bot.get_file(update.message.voice.file_id)
        file_path = f"voice_{user_id}_{update.message.message_id}.ogg"
        await new_file.download_to_drive(file_path)
        text_from_voice = transcribe_audio_free(file_path)
        if os.path.exists(file_path): os.remove(file_path)
        if not text_from_voice:
            await status_msg.edit_text("⚠️ لم أفهم الصوت.")
            return CHOOSING
        await status_msg.edit_text(f"🗣️ **سمعتك بتقول:**\n\"{text_from_voice}\"")
        reply_text = handle_message(text_from_voice, user_id)
        await update.message.reply_text(reply_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error voice: {e}")
        await status_msg.edit_text("⚠️ حدث خطأ تقني.")
    return CHOOSING

if __name__ == '__main__':
    # بناء التطبيق
    app = ApplicationBuilder().token(TOKEN).build()
    
    # 4. تفعيل نظام التذكير مع الحماية من غياب JobQueue
    if app.job_queue:
        app.job_queue.run_repeating(reminder_check_callback, interval=60, first=10)
        logger.info("⏰ Reminder System: JobQueue is active.")
    else:
        logger.error("❌ JobQueue is NOT available. Install it using: pip install 'python-telegram-bot[job-queue]'")

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_input),
            MessageHandler(filters.VOICE, handle_voice_input)
        ],
        states={
            LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_login)],
            CHOOSING: [
                CallbackQueryHandler(add_start, pattern="^add$"),
                CallbackQueryHandler(view_tasks_start, pattern="^view$"),
                CallbackQueryHandler(delete_start, pattern="^delete$"),
                MessageHandler(filters.VOICE, handle_voice_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_input)
            ],
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            ADD_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            ADD_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time)],
            ADD_TYPE: [CallbackQueryHandler(get_type)],
            ADD_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)],
            CONFIRM_CONFLICT: [CallbackQueryHandler(handle_conflict_decision)],
            DELETE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete)],
            VIEW_OPTIONS: [CallbackQueryHandler(view_options_handler)]
        },
        fallbacks=[CommandHandler('start', start)]
    )

    app.add_handler(conv_handler)
    logger.info("🚀 Bot started polling...")
    app.run_polling()