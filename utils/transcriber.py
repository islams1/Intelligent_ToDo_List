import speech_recognition as sr
from pydub import AudioSegment
import os

# الإعدادات (اللي أثبتت نجاحها في الوصول للمسار)
FFMPEG_BIN_PATH = r"Q:\ffmpeg\bin"
os.environ["PATH"] += os.pathsep + FFMPEG_BIN_PATH
AudioSegment.converter = os.path.join(FFMPEG_BIN_PATH, "ffmpeg.exe")
AudioSegment.ffprobe = os.path.join(FFMPEG_BIN_PATH, "ffprobe.exe")

def transcribe_audio_free(ogg_file_path):
    if not os.path.exists(ogg_file_path):
        return None

    wav_file_path = ogg_file_path.replace(".ogg", ".wav")

    try:
        # 1. تحويل الصوت بمواصفات قياسية (مهم جداً لجوجل)
        print(f"🎬 Converting to Standard WAV (16kHz, Mono)...")
        audio = AudioSegment.from_file(ogg_file_path)
        
        # تحويل الصوت لـ Mono وتردد 16000Hz (ده التردد المثالي للتعرف على الكلام)
        audio = audio.set_frame_rate(16000).set_channels(1)
        
        # تصدير الملف
        audio.export(wav_file_path, format="wav")

        # 2. التعرف على الكلام
        recognizer = sr.Recognizer()
        
        # رفع حساسية التعرف قليلاً
        recognizer.energy_threshold = 300 
        
        with sr.AudioFile(wav_file_path) as source:
            # تقليل مدة ضبط الضوضاء لـ 0.5 ثانية فقط عشان مياكلش أول الكلام
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = recognizer.record(source)

            print("🎙️ Sending optimized audio to Google...")
            # إرسال الطلب
            text = recognizer.recognize_google(audio_data, language="ar-EG")
            return text

    except sr.UnknownValueError:
        print("❌ Google STT: الكلام غير مفهوم. حاول تسجيل الصوت في مكان هادئ.")
        return None
    except Exception as e:
        print(f"❌ STT Detailed Error: {str(e)}")
        return None
    finally:
        # حذف ملف الـ WAV المؤقت
        if os.path.exists(wav_file_path):
            try:
                os.remove(wav_file_path)
            except:
                pass