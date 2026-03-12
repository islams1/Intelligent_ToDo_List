import os

# المسار اللي إنت حددته
test_path = r"Q:\ffmpeg\bin"

print(f"Checking folder: {test_path}")
if os.path.exists(test_path):
    print("✅ Folder Found!")
    print(f"Files inside: {os.listdir(test_path)}")
    # التأكد من وجود الملفات المطلوبة بالاسم
    if "ffmpeg.exe" in os.listdir(test_path):
        print("✅ ffmpeg.exe is HERE!")
    else:
        print("❌ ffmpeg.exe is MISSING from this folder")
else:
    print("❌ Folder NOT FOUND. Check the drive or folder name.")