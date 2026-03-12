import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import config

def send_approval_email(task_id, task_details, is_conflict=False):
    subject = f"🔔 Action Required: New Meeting Request ({task_details['type']})"
    if is_conflict:
        subject = f"⚠️ CONFLICT ALERT: Meeting Request Override"

    # روابط الموافقة والرفض
    accept_url = f"{config.BASE_URL}/approve_meeting?id={task_id}&force={str(is_conflict).lower()}"
    reject_url = f"{config.BASE_URL}/reject_meeting?id={task_id}"

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
    msg["From"] = config.EMAIL_USER
    msg["To"] = config.EMAIL_USER  # يرسل للأدمن (أنت)

    msg.attach(MIMEText(html_content, "html"))

    try:
        server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
        server.starttls()
        server.login(config.EMAIL_USER, config.EMAIL_PASSWORD)
        server.sendmail(config.EMAIL_USER, config.EMAIL_USER, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False