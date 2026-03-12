import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# إعدادات بريدك (يفضل وضعها في .env)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "islam.sherif243@gmail.com"
SENDER_PASSWORD = "eboc xtae fwtr gsmh" # App Password وليس كلمة السر العادية
BASE_URL = "https://attentional-overintellectually-ximena.ngrok-free.dev" # ⚠️ هام: هذا الرابط لازم يكون Ngrok أو سيرفر حقيقي

def send_approval_email(task_id, task_details, is_conflict=False):
    subject = f"🔔 Action Required: New Meeting Request ({task_details['type']})"
    if is_conflict:
        subject = f"⚠️ CONFLICT ALERT: Meeting Request Override"

    # روابط الموافقة والرفض
    accept_url = f"{BASE_URL}/approve_meeting?id={task_id}&force={str(is_conflict).lower()}"
    reject_url = f"{BASE_URL}/reject_meeting?id={task_id}"

    html_content = f"""
    <html>
    <body>
        <h2>طلب اجتماع جديد</h2>
        <p><b>العنوان:</b> {task_details['title']}</p>
        <p><b>التاريخ:</b> {task_details['date']} | <b>الساعة:</b> {task_details['time']}</p>
        <p><b>النوع:</b> {task_details['type']} 
           {'📍 (' + task_details['location'] + ')' if task_details['type'] == 'offline' else '🌐'}
        </p>
        <hr>
        {'<h3 style="color:red;">⚠️ تحذير: هذا الميعاد محجوز مسبقاً! الموافقة ستحذف الاجتماع القديم.</h3>' if is_conflict else ''}
        
        <a href="{accept_url}" style="background-color:green; color:white; padding:10px 20px; text-decoration:none;">✅ موافقة (Accept)</a>
        &nbsp;&nbsp;
        <a href="{reject_url}" style="background-color:red; color:white; padding:10px 20px; text-decoration:none;">❌ رفض (Reject)</a>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = SENDER_EMAIL # يرسل للأدمن (أنت)

    msg.attach(MIMEText(html_content, "html"))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False