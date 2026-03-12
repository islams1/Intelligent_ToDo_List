document.getElementById('allow-btn').addEventListener('click', () => {
    navigator.mediaDevices.getUserMedia({ audio: true })
        .then((stream) => {
            // بمجرد السماح، نوقف المايك ونغلق الصفحة
            stream.getTracks().forEach(track => track.stop());
            alert("✅ تم تفعيل المايكروفون بنجاح! يمكنك الآن استخدام الإضافة.");
            window.close(); // إغلاق التبويب
        })
        .catch((err) => {
            console.error(err);
            alert("❌ تم رفض الإذن. يرجى التأكد من إعدادات المتصفح.");
        });
});