import datetime
import os.path
import pytz
import uuid
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from utils.logger import logger, CAIRO_TZ

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'credentials.json'

# الإيميل المستهدف (التقويم الرئيسي)
CALENDAR_ID = 'islam.sherif243@gmail.com'

def add_event_to_google(task_obj):
    """إضافة حدث للتقويم مع دعم مرن لصيغ التاريخ"""
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        logger.error("❌ Google Calendar: credentials.json not found!")
        return None

    try:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)

        # 1. معالجة التوقيت بمرونة (Fix: Handle multiple date formats)
        start_str = f"{task_obj.date} {task_obj.time}"
        naive_dt = None
        
        # قائمة الصيغ المحتملة التي قد تأتي من الداتا بيز أو الذكاء الاصطناعي
        allowed_formats = [
            '%Y-%m-%d %H:%M',  # 2026-01-04 14:00 (Standard ISO)
            '%d-%m-%Y %H:%M',  # 04-01-2026 14:00 (Common)
            '%Y/%m/%d %H:%M',  # 2026/1/4 14:00 (Format causing the error)
            '%d/%m/%Y %H:%M',  # 4/1/2026 14:00
            '%Y.%m.%d %H:%M'   # 2026.01.04 14:00
        ]

        for fmt in allowed_formats:
            try:
                naive_dt = datetime.datetime.strptime(start_str, fmt)
                break # تم التعرف على الصيغة بنجاح
            except ValueError:
                continue
        
        # إذا فشلت كل الصيغ
        if not naive_dt:
            logger.error(f"❌ Date Error: Could not parse date '{start_str}' with any known format.")
            return None
        
        localized_start = CAIRO_TZ.localize(naive_dt)
        localized_end = localized_start + datetime.timedelta(hours=1)

        # 2. استخراج البيانات مع القيم الافتراضية
        meet_type = getattr(task_obj, 'type', 'online').lower()
        location = getattr(task_obj, 'location', 'Google Meet')
        created_by = getattr(task_obj, 'created_by', 'Smart Assistant')
        with_whom = getattr(task_obj, 'with_whom', 'N/A')
        priority = getattr(task_obj, 'priority', 'Medium')

        description_text = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 Details:\n"
            f"👤 Owner: {created_by}\n"
            f"👥 With: {with_whom}\n"
            f"🔥 Priority: {priority}\n"
            f"📍 Type: {meet_type.upper()}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 Added automatically via Smart Meeting Ecosystem"
        )

        # 3. بناء جسم الحدث
        event = {
            'summary': f"[{priority}] {task_obj.task}",
            'location': location,
            'description': description_text,
            'start': {
                'dateTime': localized_start.isoformat(),
                'timeZone': 'Africa/Cairo',
            },
            'end': {
                'dateTime': localized_end.isoformat(),
                'timeZone': 'Africa/Cairo',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 30},
                    {'method': 'email', 'minutes': 60},
                ],
            }
        }

        # ميزة Google Meet
        if meet_type == 'online':
            event['conferenceData'] = {
                'createRequest': {
                    'requestId': f"meet-{uuid.uuid4().hex}",
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'} 
                }
            }

        # 4. التنفيذ
        event_result = service.events().insert(
            calendarId=CALENDAR_ID, 
            body=event,
            conferenceDataVersion=1 
        ).execute()
        
        logger.info(f"✅ Google Calendar: Event '{task_obj.task}' created successfully.")
        return event_result.get('id')

    except Exception as e:
        logger.error(f"❌ Google Calendar Sync Error: {e}")
        return None

def delete_event_from_google(calendar_id):
    """حذف الحدث من التقويم"""
    if not calendar_id or str(calendar_id).lower() in ["none", "null", "failed", "error"]:
        return False

    try:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)

        service.events().delete(
            calendarId=CALENDAR_ID, 
            eventId=calendar_id
        ).execute()
        
        logger.info(f"🗑️ Google Calendar: Event {calendar_id} deleted successfully.")
        return True
    except Exception as e:
        if "410" in str(e) or "404" in str(e):
            return True
        logger.error(f"❌ Google Calendar Delete Error: {e}")
        return False