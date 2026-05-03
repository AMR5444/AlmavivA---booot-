from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import chromedriver_autoinstaller
import time, threading, requests
from datetime import datetime

from config import *

stop_flag = threading.Event()

# ================= DRIVER =================
def make_driver():
    path = chromedriver_autoinstaller.install()
    opts = Options()

    if HEADLESS_MODE:
        opts.add_argument("--headless=new")

    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(service=Service(path), options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    })
    return driver

# ================= HELPERS =================
def real_click(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.2)
    ActionChains(driver).move_to_element(el).click().perform()
    time.sleep(0.3)

def wait_no_spinner(driver, t=15):
    end = time.time() + t
    while time.time() < end:
        try:
            sp = driver.find_elements(By.CSS_SELECTOR,
                "mat-spinner,[class*='spinner'],[class*='loading']")
            if not any(s.is_displayed() for s in sp):
                return
        except:
            pass
        time.sleep(0.3)

# ================= TELEGRAM =================
def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        )
    except:
        pass

# ================= LOGIN =================
def login(driver, email, password):
    print("[LOGIN] فتح الموقع...")
    driver.get("https://egy.almaviva-visa.it/")

    # انتظر الصفحة تتحمل
    time.sleep(3)

    # لو عمل redirect للـ PKCE login مباشرة
    if "egyiam.almaviva-visa.it" in driver.current_url:
        print("[LOGIN] Redirect للـ login تلقائي ✓")
    else:
        # ابحث عن زرار الـ login في الصفحة الرئيسية
        print("[LOGIN] بندور على زرار Login...")
        login_found = False

        # جرب كل الطرق الممكنة لإيجاد زرار اللوجين
        login_xpaths = [
            # زرار أيقونة الحساب
            "//button[.//mat-icon[contains(text(),'person')]]",
            "//button[contains(@class,'account')]",
            # لينك Login مباشر
            "//a[contains(normalize-space(.),'Login')]",
            "//a[contains(normalize-space(.),'Sign in')]",
            "//button[contains(normalize-space(.),'Login')]",
            "//button[contains(normalize-space(.),'Sign in')]",
            # أي زرار فيه person icon
            "//*[contains(@class,'user') or contains(@class,'account') or contains(@class,'person')]",
        ]

        for xpath in login_xpaths:
            try:
                btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                print(f"[LOGIN] لقيناه: {btn.text.strip() or btn.get_attribute('class')}")
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(2)

                # بعد الضغط، دور على Login في القائمة المنسدلة لو ظهرت
                try:
                    login_menu = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH,
                            "//button[contains(normalize-space(.),'Login')] | //a[contains(normalize-space(.),'Login')]"))
                    )
                    driver.execute_script("arguments[0].click();", login_menu)
                    time.sleep(2)
                except:
                    pass

                # تحقق لو انتقلنا لصفحة الـ login
                if "egyiam.almaviva-visa.it" in driver.current_url:
                    login_found = True
                    break
            except:
                continue

        # لو مش لقيناش أي زرار، انتظر الـ redirect التلقائي
        if not login_found:
            print("[LOGIN] انتظار redirect تلقائي...")
            for _ in range(15):
                time.sleep(1)
                if "egyiam.almaviva-visa.it" in driver.current_url:
                    login_found = True
                    break
                # لو لقينا username field مباشرة
                try:
                    driver.find_element(By.ID, "username")
                    login_found = True
                    break
                except:
                    pass

        if not login_found:
            # آخر محاولة: افتح appointment وانتظر redirect للـ login
            print("[LOGIN] جرب عبر appointment...")
            driver.get("https://egy.almaviva-visa.it/appointment")
            for _ in range(15):
                time.sleep(1)
                if "egyiam.almaviva-visa.it" in driver.current_url:
                    break
                try:
                    driver.find_element(By.ID, "username")
                    break
                except:
                    pass

    # ⭐ انتظر حقل الـ username يظهر
    print("[LOGIN] انتظار حقول تسجيل الدخول...")
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "username"))
        )
        print("[LOGIN] ✓ حقول اللوجين ظهرت")
    except:
        # ممكن يكون logged in بالفعل
        if "egy.almaviva-visa.it" in driver.current_url and "egyiam" not in driver.current_url:
            print("[LOGIN] ✓ Logged in بالفعل")
            return True
        print(f"[LOGIN] ✗ الحقول مش ظهرت - {driver.current_url[:80]}")
        return False

    # ⭐ عبي الـ email والـ password
    try:
        u = driver.find_element(By.ID, "username")
        u.clear()
        u.send_keys(email)
        time.sleep(0.3)

        p = driver.find_element(By.ID, "password")
        p.clear()
        p.send_keys(password)
        time.sleep(0.3)

        driver.find_element(By.ID, "kc-login").click()
        print("[LOGIN] ✓ ضغطنا زرار Login")
    except Exception as e:
        print(f"[LOGIN] ✗ خطأ: {e}")
        return False

    # ⭐ انتظر الـ redirect يرجع للموقع بعد اللوجين
    print("[LOGIN] انتظار اكتمال تسجيل الدخول...")
    for _ in range(30):
        time.sleep(1)
        current = driver.current_url
        if "egy.almaviva-visa.it" in current and "egyiam" not in current:
            print("[LOGIN] ✅ تسجيل الدخول نجح!")
            return True

    print(f"[LOGIN] ✗ فشل - {driver.current_url[:80]}")
    return False

# ================= OPEN APPOINTMENT =================
def open_appointment(driver):
    driver.get("https://egy.almaviva-visa.it/")
    time.sleep(3)

    try:
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href,'appointment')]"))
        )
        real_click(driver, btn)
    except:
        driver.get("https://egy.almaviva-visa.it/appointment")

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.XPATH, "//mat-select[@formcontrolname='officeId']"))
        )
        return True
    except:
        return False

# ================= SELECT DROPDOWN =================
def select_option(driver, formcontrol, text):
    for _ in range(3):
        try:
            el = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable(
                    (By.XPATH, f"//mat-select[@formcontrolname='{formcontrol}']")
                )
            )
            real_click(driver, el)
            opts = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, "//mat-option"))
            )
            for o in opts:
                if text.lower() in o.text.lower():
                    real_click(driver, o)
                    wait_no_spinner(driver, 10)
                    time.sleep(1.5)
                    return True
        except:
            time.sleep(1)
    return False

# ================= VISA TYPE =================
def select_last_dropdown(driver, text):
    for _ in range(3):
        try:
            selects = driver.find_elements(By.XPATH, "//mat-select")
            selects = [s for s in selects if s.is_displayed()]
            el = selects[-1]
            real_click(driver, el)
            opts = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, "//mat-option"))
            )
            for o in opts:
                if text.lower() in o.text.lower():
                    real_click(driver, o)
                    wait_no_spinner(driver, 10)
                    return True
        except:
            time.sleep(1)
    return False

# ================= FILL FORM =================
def fill_form(driver, data):
    wait_no_spinner(driver, 10)

    if not select_option(driver, "officeId", data["center"]):
        return False

    if not select_option(driver, "idServiceLevel", data["service_level"]):
        return False

    if not select_last_dropdown(driver, data["visa_type"]):
        return False

    # DATE
    try:
        inp = driver.find_element(By.ID, "pickerInput")
        driver.execute_script("""
            arguments[0].removeAttribute('readonly');
            arguments[0].value=arguments[1];
            arguments[0].dispatchEvent(new Event('change',{bubbles:true}));
        """, inp, data["travel_date"])
    except:
        return False

    # DEST
    try:
        d = driver.find_element(By.XPATH, "//input[@formcontrolname='tripDestination']")
        d.clear()
        d.send_keys(data["destination"])
    except:
        return False

    # TERMS
    for cb in driver.find_elements(By.XPATH, "//input[@type='checkbox']"):
        try:
            if not cb.is_selected():
                real_click(driver, cb)
        except:
            pass

    return True

# ================= PROCEED WITH APPOINTMENT =================
def click_proceed(driver):
    print("  [PROCEED] دوس على Proceed with appointment...")

    proceed_xpaths = [
        "//button[contains(normalize-space(.),'Proceed with appointment')]",
        "//button[contains(normalize-space(.),'Proceed')]",
        "//*[contains(@class,'visasys-button')]//button",
        "//div[contains(@class,'visasys-button')]//button",
    ]

    for xpath in proceed_xpaths:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            print(f"  [PROCEED] لقيناه: '{btn.text.strip()}'")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", btn)
            print("  [PROCEED] ✅ اتضغط!")
            time.sleep(2)
            return True
        except:
            continue

    print("  [PROCEED] ✗ مش لقيناش الزرار")
    return False

# ================= CHECK =================
def check(driver):
    print("  [CHECK] Searching button...")

    btn = None
    xpaths = [
        "//button[contains(.,'Check')]",
        "//button[contains(.,'Availability')]",
        "//button[contains(.,'available')]",
        "//button[contains(.,'افحص')]",
        "//button[contains(.,'المتاحة')]",
    ]

    for xp in xpaths:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            print(f"  [CHECK] Found: {btn.text}")
            break
        except:
            continue

    if not btn:
        print("  [CHECK] Fallback to last button...")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for b in reversed(buttons):
            if b.is_displayed() and b.is_enabled():
                btn = b
                break

    if not btn:
        print("  [CHECK] Button NOT FOUND ❌")
        return False

    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", btn)
        print("  [CHECK] Clicked ✅")
    except Exception as e:
        print("  [CHECK] Click failed:", e)
        return False

    wait_no_spinner(driver, 10)
    time.sleep(3)

    page = driver.page_source.lower()

    slots_found = (
        "appointments available" in page or
        "proceed with appointment" in page
    )

    if slots_found:
        print("  [CHECK] ✅ SLOTS FOUND!")
        return True

    no_slots = (
        "no available" in page or
        "not available" in page or
        "لا يوجد" in page or
        "لا توجد" in page
    )

    if no_slots:
        print("  [CHECK] No slots ❌")
        return False

    for sel in [".available-day", "[class*='available']", "[class*='slot']"]:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            slots = [e.text.strip() for e in els if e.text.strip()]
            if slots:
                print(f"  [CHECK] ✅ SLOTS: {slots[:5]}")
                return True
        except:
            pass

    print("  [CHECK] No slots ❌")
    return False

# ================= MAIN =================
def run(acc):
    driver = make_driver()

    if not login(driver, acc["email"], acc["password"]):
        send("❌ Login failed")
        return

    notified_no_slots = False

    while True:
        if stop_flag.is_set():
            break

        if not open_appointment(driver):
            login(driver, acc["email"], acc["password"])
            continue

        if not fill_form(driver, acc["data"]):
            continue

        result = check(driver)

        if result is True:
            proceed_ok = click_proceed(driver)

            msg = (
                f"🔥 تم العثور على موعد!\n"
                f"👤 {acc['email']}\n"
                f"📋 {acc['data']['visa_type']}\n"
                f"🏢 {acc['data']['center']}\n"
                f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            if proceed_ok:
                msg += "✅ تم الضغط على Proceed — أكمل الحجز يدوياً الآن!"
            else:
                msg += "⚠️ ادخل وأكمل الحجز يدوياً الآن!"

            send(msg)
            print(f"\n✅ SLOTS FOUND! Telegram sent. Bot stopping.")
            stop_flag.set()
            break

        elif result is False:
            if not notified_no_slots:
                send(f"❌ لا يوجد مواعيد حالياً\n{acc['email']}")
                notified_no_slots = True
            print("  [LOOP] No slots... retrying")
            time.sleep(REFRESH_INTERVAL)

        else:
            print("  [CHECK] Error, retrying...")
            time.sleep(5)

    driver.quit()

# ================= START =================
def main():
    for acc in ACCOUNTS:
        threading.Thread(target=run, args=(acc,), daemon=True).start()

    while True:
        if stop_flag.is_set():
            print("\nBot stopped.")
            break
        time.sleep(1)

if __name__ == "__main__":
    main()