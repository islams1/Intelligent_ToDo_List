import gspread
from oauth2client.service_account import ServiceAccountCredentials
from database.db_manager import get_all_meetings
import json
from utils.logger import logger # ✅ إضافة اللوجر الموحد
from config import config

SHEET_NAME = "todo"

# متغير لتخزين الرابط (Caching)
CACHED_SHEET_URL = None

def get_auth_client():
    """دالة مساعدة للاتصال بجوجل"""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        credentials_data = config.GOOGLE_CREDENTIALS
        if not credentials_data:
            logger.error("❌ Google Sheets: Google credentials not found in environment variables!")
            return None
            
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_data, scope)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"❌ Google Sheets Auth Error: {e}")
        return None

def get_sheet_url():
    """جلب رابط الشيت المباشر"""
    global CACHED_SHEET_URL
    if CACHED_SHEET_URL:
        return CACHED_SHEET_URL
    try:
        client = get_auth_client()
        if not client: return None
        sheet = client.open(SHEET_NAME)
        CACHED_SHEET_URL = sheet.url 
        return sheet.url
    except Exception as e:
        logger.error(f"❌ Error getting sheet URL: {e}")
        return "https://docs.google.com/spreadsheets"

def sync_sqlite_to_sheets():
    try:
        client = get_auth_client()
        if not client: return False
        
        spreadsheet = client.open(SHEET_NAME)
        sheet = spreadsheet.sheet1
        sheet_id = sheet.id 

        meetings = get_all_meetings()

        # ✅ 1. حذف ID من الهيدر (أصبح 10 أعمدة بدلاً من 11)
        headers = ["Title", "Date", "Time", "Type", "Location", "Status", "With Whom", "Priority", "Created By", "Created At"]
        data_to_write = [headers]
        
        RED_COLOR = {"red": 0.95, "green": 0.8, "blue": 0.8}
        YELLOW_COLOR = {"red": 1.0, "green": 0.95, "blue": 0.8}
        GREEN_COLOR = {"red": 0.85, "green": 0.93, "blue": 0.83}
        HEADER_COLOR = {"red": 0.8, "green": 0.8, "blue": 0.8}

        formatting_requests = []

        # تنسيق الهيدر
        formatting_requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": HEADER_COLOR,
                        "textFormat": {"bold": True, "fontSize": 11},
                        "horizontalAlignment": "CENTER"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
            }
        })

        for index, m in enumerate(meetings):
            row_num = index + 1
            
            # ✅ 2. حذف m.get('id') من هنا لكي لا يظهر في الشيت
            row = [
                m.get('title', 'N/A'), 
                m.get('date', 'N/A'), 
                m.get('time', 'N/A'), 
                m.get('type', 'N/A'), 
                m.get('location', 'N/A'), 
                m.get('status', 'N/A'),
                m.get('with_whom', 'N/A'),
                m.get('priority', 'Medium'),
                m.get('created_by', 'Unknown'),
                m.get('created_at', 'N/A')
            ]
            data_to_write.append(row)

            priority = str(m.get('priority', 'Medium')).lower().strip()
            bg_color = RED_COLOR if "high" in priority else (YELLOW_COLOR if "medium" in priority else GREEN_COLOR)

            formatting_requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_num,
                        "endRowIndex": row_num + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(headers) # سيحسب حتى العمود العاشر
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": bg_color,
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE"
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment)"
                }
            })

        # طلب إضافة فلتر وتوسيع الأعمدة (تم تحديث النطاق آلياً باستخدام len(headers))
        formatting_requests.append({"setBasicFilter": {"filter": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": len(data_to_write), "startColumnIndex": 0, "endColumnIndex": len(headers)}}}})
        formatting_requests.append({"autoResizeDimensions": {"dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": len(headers)}}})

        sheet.clear()
        sheet.update(data_to_write)
        
        if formatting_requests:
            spreadsheet.batch_update({"requests": formatting_requests})
        
        logger.info(f"✅ Google Sheets: Synced {len(meetings)} meetings chronologically without ID.")
        return True

    except Exception as e:
        logger.error(f"❌ Google Sheets Sync Error: {e}")
        return False
# --- كود للاختبار السريع ---
if __name__ == "__main__":
    logger.info("Testing connection to Google Sheets...")
    sync_sqlite_to_sheets()