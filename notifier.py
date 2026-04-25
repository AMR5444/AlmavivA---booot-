# notifier.py
import requests
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_notification(account, slots_data=None):
    """
    إرسال إشعار لتليجرام عند وجود مواعيد
    """
    if slots_data:
        slots_text = "\n".join(slots_data) if slots_data else "مواعيد متاحة"
        message = f"""
🔔 **تم العثور على مواعيد متاحة!** 🔔

👤 **الحساب:** {account['email']}
🏢 **المركز:** {account['data']['center']}
⭐ **مستوى الخدمة:** {account['data']['service_level']}
📋 **نوع التأشيرة:** {account['data']['visa_type']}
👥 **عدد التأشيرات:** {account['data']['persons_count']}
📅 **تاريخ السفر:** {account['data']['travel_date']}
🌍 **الوجهة:** {account['data']['destination']}

✅ **المواعيد المتاحة:**
{slots_text}

🕒 **وقت الاكتشاف:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ **يجب الدخول لإكمال الحجز يدوياً فوراً!**
"""
    else:
        message = f"""
❌ **لا توجد مواعيد متاحة حالياً** ❌

👤 **الحساب:** {account['email']}
🕒 **آخر محاولة:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔄 سيتم إعادة المحاولة تلقائياً...
"""
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"[{account['email']}] Telegram notification sent ✅")
        else:
            print(f"[{account['email']}] Telegram error: {response.text}")
    except Exception as e:
        print(f"[{account['email']}] Telegram failed: {e}")