from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import chromedriver_autoinstaller
import time
import threading
import requests
from datetime import datetime

from config import (
    ACCOUNTS, REFRESH_INTERVAL, PROXY, HEADLESS_MODE,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)

stop_flag = threading.Event()
APPOINTMENT_URL = "https://egy.almaviva-visa.it/appointment"

# ============================================================
# Telegram
# ============================================================
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
        print("  [TG] Sent")
    except Exception as e:
        print(f"  [TG] Failed: {e}")

def notify_success(account, slots_data):
    slots_text = "\n".join(slots_data) if slots_data else "Slots available"
    send_telegram(
        f"✅ *SLOTS FOUND!*\n\n"
        f"👤 {account['email']}\n"
        f"📆 Slots:\n{slots_text}\n\n"
        f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⚠️ Login NOW and complete booking manually!"
    )

def notify_error(account, reason):
    send_telegram(
        f"❌ *Bot Error*\n\n"
        f"👤 {account['email']}\n"
        f"❗ {reason}\n"
        f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

# ============================================================
# Driver
# ============================================================
def get_driver():
    chromedriver_path = chromedriver_autoinstaller.install()
    print(f"  [Driver] {chromedriver_path}")
    options = Options()
    if HEADLESS_MODE:
        options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-extensions')
    options.add_argument('--ignore-certificate-errors')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    options.page_load_strategy = 'eager'
    if PROXY:
        options.add_argument(f'--proxy-server={PROXY}')
    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(0)
    return driver

def safe_get(driver, url):
    try:
        driver.get(url)
    except (TimeoutException, WebDriverException) as e:
        if "timeout" not in str(e).lower():
            raise

def js_click(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.2)
    driver.execute_script("arguments[0].click();", el)

def wait_spinner_gone(driver, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            spinners = driver.find_elements(By.CSS_SELECTOR,
                "mat-spinner, [class*='spinner'], [class*='loading']")
            if not any(s.is_displayed() for s in spinners):
                return
        except:
            pass
        time.sleep(0.3)

# ============================================================
# Login
# ============================================================
def login(driver, email, password):
    print("  [Login] Opening...")
    safe_get(driver, "https://egy.almaviva-visa.it/login")
    try:
        field = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "username"))
        )
    except:
        if "login" not in driver.current_url:
            print("  [Login] Already logged in")
            return True
        return False
    field.clear()
    field.send_keys(email)
    time.sleep(0.3)
    driver.find_element(By.ID, "password").clear()
    driver.find_element(By.ID, "password").send_keys(password)
    time.sleep(0.3)
    driver.find_element(By.ID, "kc-login").click()
    for _ in range(15):
        time.sleep(1)
        if "login" not in driver.current_url:
            print("  [Login] Success")
            return True
    print("  [Login] Failed")
    return False

# ============================================================
# Navigate to appointment page
# ============================================================
def go_to_appointment_page(driver):
    print("  [Nav] Opening appointment page...")
    safe_get(driver, APPOINTMENT_URL)

    for _ in range(10):
        time.sleep(1)
        if "appointment" in driver.current_url:
            break
    else:
        print(f"  [Nav] Wrong URL: {driver.current_url}")
        return False

    wait_spinner_gone(driver, timeout=20)

    try:
        WebDriverWait(driver, 25).until(
            EC.presence_of_element_located(
                (By.XPATH, "//mat-select[@formcontrolname='officeId']"))
        )
    except:
        print("  [Nav] Center dropdown not found")
        return False

    wait_spinner_gone(driver, timeout=10)
    time.sleep(1)
    print("  [Nav] Page ready")
    return True

# ============================================================
# Core helper: click mat-select and wait for options
# ============================================================
def click_and_get_options(driver, dropdown_el, label="", timeout=20):
    """Click a mat-select and wait until options with real text appear."""
    js_click(driver, dropdown_el)
    time.sleep(0.5)

    end = time.time() + timeout
    while time.time() < end:
        try:
            opts = driver.find_elements(By.XPATH, "//mat-option")
            loaded = [o for o in opts if o.is_displayed() and o.text.strip()]
            if loaded:
                texts = [o.text.strip() for o in loaded]
                print(f"    [{label}] Options: {texts}")
                return loaded
        except:
            pass
        time.sleep(0.5)

    # one retry
    print(f"    [{label}] Retry click...")
    js_click(driver, dropdown_el)
    end = time.time() + 10
    while time.time() < end:
        try:
            opts = driver.find_elements(By.XPATH, "//mat-option")
            loaded = [o for o in opts if o.is_displayed() and o.text.strip()]
            if loaded:
                texts = [o.text.strip() for o in loaded]
                print(f"    [{label}] Options: {texts}")
                return loaded
        except:
            pass
        time.sleep(0.5)

    print(f"    [{label}] No options loaded")
    return []

def best_match(options, target):
    t = target.strip().lower()
    for o in options:
        if o.text.strip().lower() == t:
            return o
    for o in options:
        if t in o.text.strip().lower() or o.text.strip().lower() in t:
            return o
    return None

def close_panel(driver):
    try:
        driver.find_element(By.TAG_NAME, 'body').click()
        time.sleep(0.3)
    except:
        pass

# ============================================================
# STEP 1 — Select center (officeId)
# ============================================================
def step1_center(driver, center_text):
    print("  [Step 1] Select center...")
    try:
        el = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.XPATH, "//mat-select[@formcontrolname='officeId']"))
        )
    except:
        print("  [Step 1] FAIL - not found")
        return False

    options = click_and_get_options(driver, el, "center", timeout=20)
    if not options:
        print("  [Step 1] FAIL - no options")
        return False

    chosen = best_match(options, center_text)
    if not chosen:
        avail = [o.text.strip() for o in options]
        print(f"  [Step 1] FAIL - '{center_text}' not in {avail}")
        print(f"  [Step 1] >>> Fix config 'center' to one of: {avail}")
        close_panel(driver)
        return False

    js_click(driver, chosen)
    print(f"  [Step 1] OK - '{chosen.text.strip()}'")
    wait_spinner_gone(driver, 10)
    time.sleep(1.5)  # wait for service level to appear
    return True

# ============================================================
# STEP 2 — Select service level (Standard / VIP)
# Appears right after center selection
# ============================================================
def step2_service_level(driver, service_text):
    print("  [Step 2] Select service level...")

    # Wait for idServiceLevel to appear and be enabled
    el = None
    for _ in range(20):
        try:
            candidates = driver.find_elements(
                By.XPATH, "//mat-select[@formcontrolname='idServiceLevel']")
            if not candidates:
                # fallback: second mat-select on page
                all_ms = driver.find_elements(By.XPATH, "//mat-select")
                candidates = [s for s in all_ms
                              if s.get_attribute("formcontrolname") != "officeId"]
            for c in candidates:
                if c.is_displayed() and c.get_attribute("aria-disabled") != "true":
                    el = c
                    break
        except:
            pass
        if el:
            break
        time.sleep(0.5)

    if not el:
        print("  [Step 2] FAIL - service level dropdown not found/enabled")
        return False

    fc = el.get_attribute("formcontrolname") or el.get_attribute("id") or "?"
    print(f"    [Step 2] Found: {fc}")

    options = click_and_get_options(driver, el, "service_level", timeout=15)
    if not options:
        print("  [Step 2] FAIL - no options")
        return False

    chosen = best_match(options, service_text)
    if not chosen:
        avail = [o.text.strip() for o in options]
        print(f"  [Step 2] FAIL - '{service_text}' not in {avail}")
        print(f"  [Step 2] >>> Fix config 'service_level' to one of: {avail}")
        close_panel(driver)
        return False

    js_click(driver, chosen)
    print(f"  [Step 2] OK - '{chosen.text.strip()}'")
    wait_spinner_gone(driver, 10)
    time.sleep(1.5)  # wait for visa type to appear
    return True

# ============================================================
# STEP 3 — Select visa type
# Appears after service level selection
# ============================================================
def step3_visa_type(driver, visa_text):
    print("  [Step 3] Select visa type...")

    # Wait for the 3rd mat-select: not officeId, not idServiceLevel
    el = None
    for _ in range(20):
        try:
            all_ms = driver.find_elements(By.XPATH, "//mat-select")
            for s in all_ms:
                fc = s.get_attribute("formcontrolname") or ""
                if fc in ("officeId", "idServiceLevel"):
                    continue
                if s.is_displayed() and s.get_attribute("aria-disabled") != "true":
                    el = s
                    break
        except:
            pass
        if el:
            break
        time.sleep(0.5)

    if not el:
        print("  [Step 3] FAIL - visa type dropdown not found/enabled")
        return False

    fc = el.get_attribute("formcontrolname") or el.get_attribute("id") or "?"
    print(f"    [Step 3] Found: {fc}")

    options = click_and_get_options(driver, el, "visa_type", timeout=15)
    if not options:
        print("  [Step 3] FAIL - no options")
        return False

    chosen = best_match(options, visa_text)
    if not chosen:
        avail = [o.text.strip() for o in options]
        print(f"  [Step 3] FAIL - '{visa_text}' not in {avail}")
        print(f"  [Step 3] >>> Fix config 'visa_type' to one of: {avail}")
        close_panel(driver)
        return False

    js_click(driver, chosen)
    print(f"  [Step 3] OK - '{chosen.text.strip()}'")
    wait_spinner_gone(driver, 10)
    time.sleep(0.5)
    return True

# ============================================================
# STEP 4 — Set trip date
# ============================================================
def step4_date(driver, date_value):
    print("  [Step 4] Set date...")
    try:
        parts = date_value.split('/')
        formatted = f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{parts[2]}"
        inp = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "pickerInput"))
        )
        driver.execute_script("""
            var input = arguments[0];
            input.removeAttribute('readonly');
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, arguments[1]);
            ['input','change','blur'].forEach(function(e) {
                input.dispatchEvent(new Event(e, {bubbles:true}));
            });
        """, inp, formatted)
        print(f"  [Step 4] OK - {formatted}")
        time.sleep(0.5)
        return True
    except Exception as e:
        print(f"  [Step 4] FAIL: {e}")
        return False

# ============================================================
# STEP 5 — Set destination
# ============================================================
def step5_destination(driver, destination):
    print("  [Step 5] Set destination...")
    try:
        inp = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//input[@formcontrolname='tripDestination']"))
        )
        inp.clear()
        inp.send_keys(destination)
        print(f"  [Step 5] OK - {destination}")
        time.sleep(0.3)
        return True
    except Exception as e:
        print(f"  [Step 5] FAIL: {e}")
        return False

# ============================================================
# STEP 6 — Accept terms
# ============================================================
def step6_terms(driver):
    print("  [Step 6] Accept terms...")
    count = 0
    for cb_id in ["mat-mdc-checkbox-1-input", "mat-mdc-checkbox-2-input"]:
        try:
            cb = driver.find_element(By.ID, cb_id)
            if not cb.is_selected():
                js_click(driver, cb)
                count += 1
                time.sleep(0.3)
        except:
            pass
    if count == 0:
        for cb in driver.find_elements(By.XPATH, "//input[@type='checkbox']"):
            try:
                if not cb.is_selected() and cb.is_displayed():
                    js_click(driver, cb)
                    count += 1
                    time.sleep(0.3)
            except:
                pass
    print(f"  [Step 6] OK - {count} checked")

# ============================================================
# STEP 7 — Click Check Availability & parse result
# ============================================================
def step7_check_availability(driver):
    print("  [Step 7] Clicking Check Availability...")

    btn = None
    xpaths = [
        "//button[contains(normalize-space(.), 'افحص الاماكن المتاحة')]",
        "//button[contains(normalize-space(.), 'افحص الأماكن المتاحة')]",
        "//button[contains(normalize-space(.), 'الاماكن المتاحة')]",
        "//button[contains(normalize-space(.), 'Check availability')]",
        "//button[contains(normalize-space(.), 'Check Availability')]",
        "//button[contains(normalize-space(.), 'Check')]",
        "//button[@type='submit']",
    ]
    for xpath in xpaths:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            print(f"    [Step 7] Button: '{btn.text.strip()}'")
            break
        except:
            continue

    if not btn:
        try:
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for b in buttons:
                txt = b.text.strip().lower()
                if b.is_displayed() and b.is_enabled() and txt and "login" not in txt:
                    btn = b
                    print(f"    [Step 7] Fallback: '{b.text.strip()}'")
                    break
        except:
            pass

    if not btn:
        print("  [Step 7] FAIL - button not found")
        return False, None

    js_click(driver, btn)
    print("  [Step 7] Clicked!")
    wait_spinner_gone(driver, timeout=15)
    time.sleep(3)

    # Parse result
    page = driver.page_source.lower()
    for kw in ["no available", "not available", "no slots", "لا توجد مواعيد", "لا يوجد", "لا توجد أماكن", "no appointment"]:
        if kw in page:
            print("  [Step 7] No slots available")
            return False, None

    for sel in [".available-day", "[class*='available']",
                "[class*='slot']", "[class*='calendar']", "mat-card"]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        slots = [e.text.strip() for e in els if e.text.strip()]
        if slots:
            print(f"  [Step 7] ✅ SLOTS: {slots[:5]}")
            return True, slots[:5]

    print("  [Step 7] Result page loaded - no slot elements found")
    return False, None

# ============================================================
# Run full form
# ============================================================
def fill_and_check(driver, data):
    print("\n  ===== FORM START =====")
    wait_spinner_gone(driver, 10)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)

    if not step1_center(driver, data["center"]):
        return False, None
    if not step2_service_level(driver, data["service_level"]):
        return False, None
    if not step3_visa_type(driver, data["visa_type"]):
        return False, None
    if not step4_date(driver, data["travel_date"]):
        return False, None
    if not step5_destination(driver, data["destination"]):
        return False, None
    step6_terms(driver)
    print("  ===== FORM FILLED ✅ =====")

    return step7_check_availability(driver)

# ============================================================
# Main loop
# ============================================================
def run_forever(driver, account):
    email = account["email"]
    data = account["data"]
    print(f"\n[{email}] Started - every {REFRESH_INTERVAL}s")

    attempt = 0
    fail_count = 0

    while not stop_flag.is_set():
        attempt += 1

        try:
            _ = driver.current_url
        except:
            notify_error(account, "Browser closed")
            break

        try:
            if not go_to_appointment_page(driver):
                fail_count += 1
                time.sleep(5)
                continue

            has_slots, slots = fill_and_check(driver, data)

            if has_slots:
                notify_success(account, slots)
                print(f"[{email}] ✅✅✅ SLOTS FOUND! attempt #{attempt}")
                stop_flag.set()
                return True

            # has_slots=False, slots=None means a step failed
            # has_slots=False, slots=[] means form worked but no slots
            fail_count = 0 if slots is not None else fail_count + 1

            if fail_count >= 5:
                notify_error(account, f"Form failed {fail_count}x in a row")
                fail_count = 0
                login(driver, email, account["password"])
                time.sleep(3)
            elif attempt % 5 == 0:
                print(f"[{email}] Attempt #{attempt} - still searching...")

        except WebDriverException as e:
            err = str(e).lower()
            if "invalid session" in err or "disconnected" in err:
                notify_error(account, "Browser disconnected")
                break
            print(f"[{email}] WebDriverError: {e}")
            time.sleep(3)
        except Exception as e:
            print(f"[{email}] Error: {e}")
            time.sleep(3)

        time.sleep(REFRESH_INTERVAL)

    return False

# ============================================================
# Run account
# ============================================================
def run_account(account):
    driver = None
    email = account["email"]
    try:
        print(f"\n{'='*50}\nStarting: {email}\n{'='*50}")
        driver = get_driver()
        if not login(driver, email, account["password"]):
            notify_error(account, "Login failed")
            return
        run_forever(driver, account)
    except Exception as e:
        print(f"[{email}] FATAL: {e}")
        notify_error(account, str(e)[:100])
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
            print(f"[{email}] Browser closed")

# ============================================================
# Entry point
# ============================================================
def main():
    print("""
    ╔════════════════════════════════════════════╗
    ║     Almaviva Booking Bot v8.4              ║
    ║  center→service→visa→date→dest→CHECK       ║
    ╚════════════════════════════════════════════╝
    """)
    print(f"Interval: {REFRESH_INTERVAL}s | Accounts: {len(ACCOUNTS)}")

    threads = []
    for account in ACCOUNTS:
        t = threading.Thread(target=run_account, args=(account,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(2)

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\nStopped manually")
        stop_flag.set()

    print("\nBot finished.")

if __name__ == "__main__":
    main()