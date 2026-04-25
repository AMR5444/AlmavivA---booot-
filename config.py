# config.py
TELEGRAM_BOT_TOKEN = "8792137870:AAFXvOEfpFcc-fnx9JqDd8BIsuh_E7XT8P4"
TELEGRAM_CHAT_ID = "1300642644"

REFRESH_INTERVAL = 3
PROXY = None
HEADLESS_MODE = False

# Form order (confirmed from screenshot):
# 1. center        → Select the center
# 2. service_level → Select service level  (appears after center)
# 3. visa_type     → Select the visa type  (appears after service level)
# 4. travel_date   → Trip date
# 5. destination   → Destination
# 6. Terms checkboxes
# 7. Check Availability button

ACCOUNTS = [
    {
        "email": "asmaa.lashin99@outlook.com",
        "password": "Aa112233@",
        "data": {
            "center":        "Cairo",
            "service_level": "Standard",   # Standard - EGP 1875  او  Vip - EGP 4082
            "visa_type":     "Study",       # هيطبع الخيارات في اللوج لو غلط
            "travel_date":   "26/04/2026",
            "destination":   "roma"
        }
    },
]