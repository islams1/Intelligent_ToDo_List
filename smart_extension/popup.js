// smart_extension/popup.js

const SERVER_URL = "http://127.0.0.1:8000";

let userEmail = localStorage.getItem('smart_bot_email');
const chatBox = document.getElementById('chat-box');
const msgInput = document.getElementById('msg-input');
const recordBtn = document.getElementById('record-btn');
const loginScreen = document.getElementById('login-screen');
const loginBtn = document.getElementById('login-btn');
const logoutBtn = document.getElementById('logout-btn');

let mediaRecorder;
let audioChunks = [];
let recordedMimeType = 'audio/webm'; // المتغير لتخزين النوع المدعوم

document.addEventListener('DOMContentLoaded', () => {
    if (userEmail) {
        loginScreen.style.display = 'none';
        addMessage(`🔑 Logged in as: ${userEmail}`, false);
    }

    loginBtn.addEventListener('click', login);
    logoutBtn.addEventListener('click', logout);
    msgInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
    
    recordBtn.addEventListener('mousedown', startRecording);
    recordBtn.addEventListener('mouseup', stopRecording);
    // دعم اللمس للموبايل
    recordBtn.addEventListener('touchstart', (e) => { e.preventDefault(); startRecording(e); });
    recordBtn.addEventListener('touchend', (e) => { e.preventDefault(); stopRecording(e); });
});

async function login() {
    const emailInput = document.getElementById('email-input');
    const email = emailInput.value.trim().toLowerCase();
    
    if (!email || !email.includes('@')) {
        alert('Please enter a valid email format.');
        return;
    }

    const originalText = loginBtn.innerText;
    loginBtn.innerText = "Checking...";
    loginBtn.disabled = true;

    try {
        const response = await fetch(`${SERVER_URL}/api/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email })
        });
        
        const data = await response.json();

        if (response.ok && data.success) {
            userEmail = email;
            localStorage.setItem('smart_bot_email', email);
            loginScreen.style.display = 'none';
            addMessage(`👋 Welcome back, **${data.name}**! (${data.role})`, false);
        } else {
            alert(data.message || "Login failed.");
        }

    } catch (error) {
        console.error(error);
        alert("⚠️ Could not connect to server. Ensure main.py is running.");
    } finally {
        loginBtn.innerText = originalText;
        loginBtn.disabled = false;
    }
}

function logout() {
    localStorage.removeItem('smart_bot_email');
    location.reload();
}

function addMessage(text, isUser = false) {
    const div = document.createElement('div');
    div.className = `message ${isUser ? 'user-msg' : 'bot-msg'}`;
    div.innerHTML = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function sendMessage() {
    const text = msgInput.value.trim();
    if (!text) return;

    addMessage(text, true);
    msgInput.value = '';

    try {
        const response = await fetch(`${SERVER_URL}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, email: userEmail })
        });
        const data = await response.json();
        addMessage(data.reply);
    } catch (error) {
        addMessage("⚠️ Error: Check if server is running.");
    }
}

// --- 🎤 منطق الصوت المحدث (Bulletproof Logic) ---

async function startRecording(e) {
    // التحقق من أن المستخدم مسجل دخول
    if (!userEmail) { 
        alert("Please login first."); 
        return; 
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        
        // ✅ 1. تحديد أفضل صيغة يدعمها المتصفح
        const mimeTypes = [
            'audio/webm;codecs=opus', // الأفضل والأحدث
            'audio/webm',             // القياسي
            'audio/ogg'               // بديل
        ];

        recordedMimeType = mimeTypes.find(type => MediaRecorder.isTypeSupported(type)) || '';

        if (!recordedMimeType) {
            alert("No supported audio mime type found!");
            return;
        }

        const options = { mimeType: recordedMimeType };
        mediaRecorder = new MediaRecorder(stream, options);
        audioChunks = [];

        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            // ✅ 2. استخدام نفس الصيغة عند التجميع
            const audioBlob = new Blob(audioChunks, { type: recordedMimeType });
            
            // ✅ 3. التحقق من حجم الملف (تجاهل التسجيلات القصيرة جداً/الفارغة)
            if (audioBlob.size < 1000) { 
                console.warn("Recording too short or empty, skipping send.");
                stream.getTracks().forEach(track => track.stop());
                return;
            }

            sendAudio(audioBlob);
            stream.getTracks().forEach(track => track.stop());
        };

        mediaRecorder.start();
        recordBtn.classList.add('recording');
    } catch (err) {
        console.error("Mic Error:", err);
        // فتح صفحة الإذن إذا تم الرفض
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
            chrome.tabs.create({ url: "permission.html" });
        } else {
            alert("Microphone Error: " + err.message);
        }
    }
}

function stopRecording(e) {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        recordBtn.classList.remove('recording');
    }
}

async function sendAudio(blob) {
    const formData = new FormData();
    // إرسال الامتداد الصحيح بناءً على ما تم تسجيله
    const ext = recordedMimeType.includes('ogg') ? 'ogg' : 'webm';
    formData.append("file", blob, `ext_voice.${ext}`);
    formData.append("email", userEmail);

    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message user-msg';
    loadingDiv.innerText = '🎤 Sending...';
    chatBox.appendChild(loadingDiv);

    try {
        const response = await fetch(`${SERVER_URL}/api/voice`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) throw new Error("Server error");

        const data = await response.json();
        
        loadingDiv.remove();
        if(data.message) addMessage(data.message, true); // النص الذي سمعه جوجل
        addMessage(data.reply); // رد البوت
        
    } catch (error) {
        loadingDiv.remove();
        addMessage("⚠️ Voice processing failed.");
        console.error(error);
    }
}