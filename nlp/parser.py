# nlp/parser.py
from dateparser.search import search_dates
from datetime import datetime

def parse_free_text(text):
    # البحث عن أي تواريخ أو مواعيد داخل النص
    # settings دي بتخلي بكرة يعني بكرة حقيقي مش أي تاريخ قديم
    results = search_dates(text, languages=['ar'], settings={'PREFER_DATES_FROM': 'future'})
    
    if results:
        # results[0][0] هو النص اللي لقطه (مثلاً: "الساعة 9 بليل")
        # results[0][1] هو كائن الوقت الحقيقي (datetime object)
        time_text_found = results[0][0]
        parsed_dt = results[0][1]
        
        # تنظيف اسم المهمة: بنشيل الجزء بتاع الوقت من الجملة الأصلية
        task_name = text.replace(time_text_found, "").strip()
        
        # لو المستخدم كتب وقت بس، هنحط اسم افتراضي
        if not task_name:
            task_name = "New Task"
            
        return {
            "task": task_name,
            "date": str(parsed_dt.date()),
            "time": parsed_dt.strftime("%H:%M") # هنا هيطلع 21:00 لو قلت 9 بليل
        }
    
    # لو ملقاش أي وقت في الكلام، بياخد وقت دلوقتي كاحتياطي
    return {
        "task": text,
        "date": str(datetime.now().date()),
        "time": datetime.now().strftime("%H:%M")
    }