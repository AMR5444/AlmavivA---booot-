# config.py
TELEGRAM_BOT_TOKEN = "8792137870:AAFXvOEfpFcc-fnx9JqDd8BIsuh_E7XT8P4"
TELEGRAM_CHAT_ID   = "1300642644"

REFRESH_INTERVAL = 5   # ثواني بين كل محاولة
PROXY        = None
HEADLESS_MODE = False

ACCOUNTS = [
    {
        "email":    "asmaa.lashin99@outlook.com",
        "password": "Aa112233@",
        "data": {
            "center":        "Cairo",
            "service_level": "Standard",   # Standard - EGP 1875
            "visa_type":     "Study Visa (D)",      # اللوج هيطبع الخيارات لو غلط
            "travel_date":   "4/05/2026",
            "destination":   "roma"
        }
    },
]