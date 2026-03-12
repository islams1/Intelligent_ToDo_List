import sqlite3
import os
import logging
import pytz
from datetime import datetime, timedelta

# --- 1. إعداد نظام الـ Logging والـ Timezone ---
CAIRO_TZ = pytz.timezone('Africa/Cairo')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("system_logs.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("DB_Manager")

def get_now():
    """جلب الوقت الحالي بتوقيت القاهرة"""
    return datetime.now(CAIRO_TZ)

# --- 2. إعداد المسارات ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "smart_ecosystem.db")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # جدول الاجتماعات مع Composite Primary Key (date, time)
    c.execute('''
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER UNIQUE, 
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            type TEXT NOT NULL,
            location TEXT,
            with_whom TEXT,
            priority TEXT,
            status TEXT DEFAULT 'pending',
            requester_id INTEGER,
            created_by TEXT,
            created_at TEXT,
            calendar_id TEXT,
            reminder_sent INTEGER DEFAULT 0,
            PRIMARY KEY (date, time)
        )
    ''')

    # جدول المستخدمين
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            telegram_id INTEGER,
            role TEXT DEFAULT 'user',
            name TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info(f"✅ Database initialized at: {DB_NAME}")

def seed_users():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    users = [
        ("islam.sherif243@gmail.com", "admin", "Mr. Mohamed Youssef"), 
        ("ugroup844@gmail.com", "user", "Islam Sherif"),
        ("user@company.com", "user", "Employee Name")
    ]
    for email, role, name in users:
        c.execute("INSERT OR IGNORE INTO users (email, role, name) VALUES (?, ?, ?)", (email, role, name))
    conn.commit()
    conn.close()

# --- 3. دوال المستخدمين ---

def login_user(telegram_id, email):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT role, name FROM users WHERE email=?", (email,))
    result = c.fetchone()
    if result:
        c.execute("UPDATE users SET telegram_id=? WHERE email=?", (telegram_id, email))
        conn.commit()
        conn.close()
        return {"role": result[0], "name": result[1]}
    conn.close()
    return None

def logout_user(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET telegram_id=NULL WHERE telegram_id=?", (telegram_id,))
    conn.commit()
    conn.close()

def get_user_role(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT role, name, email FROM users WHERE telegram_id=?", (telegram_id,))
    result = c.fetchone()
    conn.close()
    if result:
        return {"role": result[0], "name": result[1], "email": result[2]}
    return None

# --- 4. دوال الاجتماعات (تتضمن الدالة المطلوبة) ---

def add_meeting(title, date, time, m_type, location, with_whom, priority, requester_id, created_by, status="pending"):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        created_at = get_now().strftime("%Y-%m-%d %H:%M:%S")
        
        # توليد ID يدوي
        c.execute("SELECT MAX(id) FROM meetings")
        max_id = c.fetchone()[0]
        new_id = (max_id + 1) if max_id else 1

        c.execute('''
            INSERT INTO meetings (id, title, date, time, type, location, with_whom, priority, requester_id, created_by, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (new_id, title, date, time, m_type, location, with_whom, priority, requester_id, created_by, created_at, status))
        
        conn.commit()
        conn.close()
        return new_id
    except sqlite3.IntegrityError:
        logger.warning(f"Conflict: Slot {date} {time} taken.")
        return None

def get_all_meetings():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # ✅ التعديل هنا: الترتيب حسب التاريخ تصاعدياً ثم الوقت تصاعدياً
    c.execute("SELECT * FROM meetings ORDER BY date ASC, time ASC")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

# ✅ الدالة التي كانت مفقودة وتسببت في الخطأ
def get_meetings_in_range(start_date_str, end_date_str):
    """جلب الاجتماعات خلال فترة زمنية محددة"""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        query = '''
            SELECT * FROM meetings 
            WHERE date >= ? AND date <= ? 
            ORDER BY date ASC, time ASC
        '''
        c.execute(query, (start_date_str, end_date_str))
        rows = [dict(row) for row in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error in get_meetings_in_range: {e}")
        return []

def get_meeting_at(date, time):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM meetings WHERE date=? AND time=?", (date, time))
    row = c.fetchone()
    conn.close()
    return row

def get_meeting_by_id(m_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM meetings WHERE id=?", (m_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_meeting_status(m_id, status, calendar_id=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if calendar_id:
        c.execute("UPDATE meetings SET status=?, calendar_id=? WHERE id=?", (status, calendar_id, m_id))
    else:
        c.execute("UPDATE meetings SET status=? WHERE id=?", (status, m_id))
    conn.commit()
    conn.close()

def delete_meeting_by_id(m_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM meetings WHERE id=?", (m_id,))
    conn.commit()
    conn.close()

def suggest_slots(date_str):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        work_hours = [f"{h:02d}:00" for h in range(9, 19)]
        suggestions = []
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
        now = get_now()
        
        for i in range(2):
            check_day = target_date + timedelta(days=i)
            day_str = check_day.strftime("%Y-%m-%d")
            c.execute("SELECT time FROM meetings WHERE date=? AND status='confirmed'", (day_str,))
            booked = [row[0] for row in c.fetchall()]
            available = [slot for slot in work_hours if slot not in booked]
            if available:
                day_label = "Today" if i == 0 else "Tomorrow"
                suggestions.append(f"📅 {day_label} ({day_str}): {', '.join(available[:3])}")
            if len(suggestions) >= 2: break 
        conn.close()
        return suggestions
    except Exception as e:
        logger.error(f"Error in suggest_slots: {e}")
        return []

def get_user_role_by_email(email):
    """جلب بيانات المستخدم عن طريق الإيميل (للويب)"""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT role, name, email, telegram_id FROM users WHERE email=?", (email,))
        result = c.fetchone()
        conn.close()
        if result:
            return {
                "role": result[0], 
                "name": result[1], 
                "email": result[2],
                "telegram_id": result[3]
            }
        return None
    except Exception as e:
        logger.error(f"DB Error (get_user_role_by_email): {e}")
        return None
    
def delete_all_meetings_force():
    """حذف جميع الاجتماعات من الداتا بيز وإرجاع قائمة بالـ Calendar IDs لحذفها من جوجل"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # جلب كل الـ Calendar IDs قبل الحذف
    c.execute("SELECT calendar_id FROM meetings WHERE calendar_id IS NOT NULL")
    calendar_ids = [row[0] for row in c.fetchall()]
    
    # حذف الكل
    c.execute("DELETE FROM meetings")
    conn.commit()
    conn.close()
    
    return calendar_ids    
# تشغيل التهيئة
init_db()
seed_users()