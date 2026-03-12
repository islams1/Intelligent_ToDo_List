import json
import re
from datetime import datetime, timedelta
import google.generativeai as genai

# استيراد الأدوات
from utils.logger import logger, CAIRO_TZ
from database.db_manager import (
    add_meeting, get_all_meetings, delete_meeting_by_id, 
    get_meeting_at, update_meeting_status, get_meetings_in_range,
    get_user_role, suggest_slots, get_user_role_by_email,
    delete_all_meetings_force
)
from google_sync.google_calendar import add_event_to_google, delete_event_from_google
from google_sync.google_sheets import sync_sqlite_to_sheets, get_sheet_url
from utils.email_sender import send_approval_email

# --- إعدادات Google Gemini ---
GOOGLE_API_KEY = "AIzaSyDtcgdabbcuETcggF9EwzyI19KTqn88Qp0" 

genai.configure(api_key=GOOGLE_API_KEY)
# نستخدم موديل فلاش لأنه سريع وذكي في التحويلات الرياضية للتواريخ
model = genai.GenerativeModel('gemini-2.5-flash')

class TaskObj:
    """كائن مساعد لنقل البيانات إلى Google Calendar"""
    def __init__(self, **entries):
        self.__dict__.update(entries)
        if 'title' in entries: self.task = entries['title']
        # ✅ تحديث القيم الافتراضية هنا أيضاً
        self.type = entries.get('type', 'offline')
        self.location = entries.get('location', 'الشركة')
        self.created_by = entries.get('created_by', 'AI Assistant')
        self.with_whom = entries.get('with_whom', 'N/A')
        self.priority = entries.get('priority', 'Low')

def validate_datetime(date_str, time_str):
    """
    دالة للتحقق من أن التاريخ والوقت بصيغة رقمية صحيحة
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        datetime.strptime(time_str, "%H:%M")
        return True
    except (ValueError, TypeError):
        return False

def handle_message(text, user_id, email=None):
    # إعداد التوقيت
    now = datetime.now(CAIRO_TZ)
    current_moment = now.strftime("%Y-%m-%d %H:%M:%S")
    today_str = now.strftime("%Y-%m-%d")
    
    # 1. التحقق من الهوية والصلاحيات
    user_info = None
    
    if email:
        user_info = get_user_role_by_email(email)
    elif user_id:
        user_info = get_user_role(user_id)
        
    if not user_info:
        logger.warning(f"🔒 Unauthorized access attempt. ID: {user_id}, Email: {email}")
        return "🔒 أنت غير مسجل دخول. يرجى التأكد من تسجيل بياناتك لدى الأدمن."
    
    is_admin = (user_info['role'] == 'admin')
    creator_name = user_info['name']

    # --- 2. هندسة الطلب (Updated Prompt with Defaults) ---
    prompt = f"""
    You are a Smart Meeting Scheduler. 
    Current Reference Time: {current_moment} (Cairo Timezone).

    Analyze user input: "{text}".

    Your main task is to extract details and CONVERT all relative dates/times to EXACT ISO formats.

    CRITICAL FORMATTING RULES (STRICT):
    1. "date": MUST be "YYYY-MM-DD". 
       - If user says "tomorrow", calculate it based on Current Time.
       - NEVER return Arabic text like "بكرة" or "الخميس".
    2. "time": MUST be "HH:MM" (24-hour format). 
       - "5 pm" -> "17:00".
       - NEVER return "المغرب" or "العشاء".
    3. "title": The topic of the meeting.

    DEFAULT VALUES (If not specified):
    - Priority: "Low"
    - Type: "offline"
    - Location: "الشركة" (The Company)
    
    NOTE: If user mentions "Online/Zoom/Meet", set type="online" and location="Google Meet".

    INTENT RULES:
    1. "Delete everything", "Clear all" -> intent: "delete_all"
    2. "Delete [Topic]" -> intent: "delete"
    3. "View/Show schedule" -> intent: "view"
    4. "Add/Book [Topic]" -> intent: "add"
    5. Chat/Greeting -> intent: "chat"

    Return JSON ONLY:
    {{
        "intent": "add/view/delete/delete_all/chat", 
        "reply": "string (only for chat)",
        "title": "string", 
        "date": "YYYY-MM-DD", 
        "time": "HH:MM", 
        "start_date": "YYYY-MM-DD",
        "end_date": "YYYY-MM-DD",
        "type": "online/offline", 
        "location": "string", 
        "with_whom": "string", 
        "priority": "High/Medium/Low"
    }}
    """

    try:
        logger.info("🤖 Sending request to Google Gemini...")
        response = model.generate_content(prompt)
        ai_response = response.text

        clean_text = re.sub(r"```json|```", "", ai_response).strip()
        match = re.search(r"\{.*\}", clean_text, re.DOTALL)
        
        if not match: 
            return "🤔 لم أفهم الطلب بوضوح."
        
        parsed = json.loads(match.group(0))
        intent = parsed.get("intent", "chat")

        if intent == "chat":
            return parsed.get("reply", "أنا بخير، شكراً لسؤالك! كيف يمكنني مساعدتك؟")

        # ==================== LOGIC: DELETE ALL ====================
        if intent == "delete_all":
            if not is_admin: 
                return "⛔ عذراً، هذا الأمر متاح للأدمن فقط."
            
            ids_to_delete = delete_all_meetings_force()
            deleted_count = 0
            if ids_to_delete:
                for cal_id in ids_to_delete:
                    delete_event_from_google(cal_id)
                    deleted_count += 1
            
            sync_sqlite_to_sheets()
            return f"🗑️ **تمت إعادة ضبط النظام!**\nتم مسح {deleted_count} اجتماع."

        # ==================== LOGIC: ADD ====================
        if intent == "add":
            title = parsed.get("title")
            date = parsed.get("date")
            time = parsed.get("time")

            # التحقق من صحة التاريخ
            if not validate_datetime(date, time):
                logger.error(f"Invalid Date Format from AI: Date={date}, Time={time}")
                return "⚠️ لم أستطع تحديد التاريخ أو الوقت بدقة. يرجى المحاولة بصيغة أوضح."

            if not title or title.lower() == "n/a":
                return "يرجى تحديد عنوان الاجتماع."

            # ✅ تطبيق القيم الافتراضية (Python Force Logic)
            
            # 1. الأولوية (Default: Low)
            priority = parsed.get("priority")
            if not priority or priority.lower() in ["n/a", "none"]:
                priority = "Low"

            # 2. النوع والمكان (Default: Offline / الشركة)
            meet_type = parsed.get("type")
            location = parsed.get("location")

            if not meet_type or meet_type.lower() in ["n/a", "none"]:
                meet_type = "offline"
            
            if not location or location.lower() in ["n/a", "none"]:
                if meet_type == "online":
                    location = "Google Meet"
                else:
                    location = "الشركة"

            with_whom = parsed.get("with_whom", "N/A")
            if with_whom in ["ضيف", "احجز", "سجل"]: with_whom = "N/A"

            # فحص التعارض
            conflict = get_meeting_at(date, time)
            if conflict:
                suggestions = suggest_slots(date)
                msg = f"❌ **الموعد {time} يوم {date} محجوز مسبقاً!**\nالاجتماع: **'{conflict[1]}'**.\n\n"
                if suggestions:
                    msg += "💡 **مواعيد بديلة متاحة:**\n" + "\n".join([f"▫️ {s}" for s in suggestions])
                return msg

            requester_db_id = user_id if user_id else 0

            # ✅ إضافة الاجتماع (بالقيم المحسوبة)
            task_id = add_meeting(title, date, time, meet_type, location, with_whom, priority, requester_db_id, creator_name, "confirmed" if is_admin else "pending")

            # التحقق من نجاح الحفظ
            if not task_id:
                return "⚠️ حدث خطأ أثناء حفظ الاجتماع في قاعدة البيانات."

            if is_admin:
                task_obj = TaskObj(title=title, date=date, time=time, type=meet_type, location=location, with_whom=with_whom, priority=priority, created_by=creator_name)
                cal_id = add_event_to_google(task_obj)
                update_meeting_status(task_id, "confirmed", cal_id)
                sync_sqlite_to_sheets()
                return f"✅ **تم الحجز المباشر (Admin):**\n📌 {title}\n📍 {location}\n⚡ {priority}\n📅 {date} | ⏰ {time}"
            else:
                email_data = {'title': title, 'date': date, 'time': time, 'type': meet_type, 'location': location, 'with_whom': with_whom, 'priority': priority}
                send_approval_email(task_id, email_data)
                sync_sqlite_to_sheets()
                return f"📨 **تم إرسال طلب حجزك للأدمن.**\n📌 {title} | ⏰ {time}"

        # ==================== LOGIC: VIEW ====================
        elif intent == "view":
            if not is_admin: 
                return "⛔ عذراً، عرض جدول المواعيد متاح للأدمن فقط."

            start_date = parsed.get("start_date") or today_str
            end_date = parsed.get("end_date")
            
            if not end_date:
                end_date = (now + timedelta(days=7)).strftime("%Y-%m-%d")
                period_msg = " (7 أيام)"
            else:
                period_msg = ""

            meetings = get_meetings_in_range(start_date, end_date)
            sheet_url = get_sheet_url()
            
            if not meetings: 
                return f"📭 لا يوجد اجتماعات في هذه الفترة.{period_msg}\n[فتح الشيت]({sheet_url})"
            
            msg = f"📋 **جدول الاجتماعات{period_msg}:**\n"
            msg += f"📅 من {start_date} إلى {end_date}\n\n"
            
            for m in meetings:
                msg += (
                    f"■ **{m['title']}**\n"
                    f"   📅 {m['date']} ⏰ {m['time']}\n\n"
                )
            return msg + f"📂 [فتح Google Sheet كامل]({sheet_url})"

        # ==================== LOGIC: DELETE ====================
        elif intent == "delete":
            if not is_admin: 
                return "⛔ صلاحية الحذف للأدمن فقط."
                
            target_name = parsed.get("title")
            all_meetings = get_all_meetings()
            target = next((m for m in all_meetings if target_name.lower() in m['title'].lower()), None)
            if target:
                if target.get('calendar_id'): delete_event_from_google(target['calendar_id'])
                delete_meeting_by_id(target['id'])
                sync_sqlite_to_sheets()
                return f"🗑️ تم حذف اجتماع: '{target['title']}'."
            return f"⚠️ لم أجد اجتماعاً بعنوان '{target_name}'."

        return "🤔 لم أفهم طلبك بشكل صحيح."

    except Exception as e:
        logger.error(f"⚠️ Critical System Error in message_router: {e}")
        return "⚠️ حدث خطأ تقني في معالجة طلبك."