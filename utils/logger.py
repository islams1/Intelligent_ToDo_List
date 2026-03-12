import logging
import pytz
from datetime import datetime

# إعداد التوقيت
CAIRO_TZ = pytz.timezone('Africa/Cairo')

def get_now():
    return datetime.now(CAIRO_TZ)

# إعداد الـ Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("system_logs.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SmartMeetingEcosystem")