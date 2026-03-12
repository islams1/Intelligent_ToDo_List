# check_models.py
import google.generativeai as genai

GEMINI_API_KEY = "AIzaSyAJXDBkCl4sGCmVlxLinunwbff9YWzDO84"
genai.configure(api_key=GEMINI_API_KEY)

print("جاري البحث عن الموديلات المتاحة...")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
except Exception as e:
    print(f"Error: {e}")