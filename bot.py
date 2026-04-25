# bot.py - v7.6 - Fix: wait for Angular stability before interacting
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, WebDriverException, StaleElementReferenceException
)
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
        print("  [Telegram] Sent")
    except Exception as e:
        print(f"  [Telegram] Failed: {e}")

def notify_success(account, slots_data):
    slots_text = "\n".join(slots_data) if slots_data else "Available slots found"
    send_telegram(
        f"✅ *Slots Found!*\n\n"
        f"👤 {account['email']}\n"
        f"📆 Slots:\n{slots_text}\n\n"
        f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⚠️ Login now and complete booking manually!"
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

def js_click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(0.2)
    driver.execute_script("arguments[0].click();", element)

# ============================================================
# ⭐ Wait for Angular to finish all pending HTTP requests
# ============================================================
def wait_for_angular(driver, timeout=30):
    """
    Wait until Angular has no pending HTTP requests and is stable.
    Debug showed: Angular stable=False right after page load,
    then stable=True after a few seconds when API calls finish.
    """
    print("  [Angular] Waiting for Angular to stabilize...")
    start = time.time()

    js_check = """
        try {
            var testabilities = window.getAllAngularTestabilities
                ? window.getAllAngularTestabilities()
                : [];
            if (testabilities.length === 0) return true;
            return testabilities.every(function(t) { return t.isStable(); });
        } catch(e) {
            return true;
        }
    """

    while time.time() - start < timeout:
        try:
            is_stable = driver.execute_script(js_check)
            if is_stable:
                elapsed = round(time.time() - start, 1)
                print(f"  [Angular] Stable after {elapsed}s")
                return True
        except:
            pass
        time.sleep(0.5)

    print("  [Angular] Timeout waiting for stability - proceeding anyway")
    return False

# ============================================================
# Login
# ============================================================
def login(driver, email, password):
    print("  [Login] Opening login page...")
    safe_get(driver, "https://egy.almaviva-visa.it/login")
    try:
        field = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "username"))
        )
    except:
        if "login" not in driver.current_url:
            print("  [Login] Already logged in")
            return True
        print("  [Login] Could not load login page")
        return False

    field.clear()
    field.send_keys(email)
    time.sleep(0.3)
    driver.find_element(By.ID, "password").clear()
    driver.find_element(By.ID, "password").send_keys(password)
    time.sleep(0.3)
    driver.find_element(By.ID, "kc-login").click()
    print("  [Login] Submitted")

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
    print("  [Nav] Going to appointment page...")
    safe_get(driver, "https://egy.almaviva-visa.it/appointment")

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "mat-select[formcontrolname='officeId']")
            )
        )
    except TimeoutException:
        print("  [Nav] officeId element not found")
        return False

    # ⭐ Wait for Angular API calls to complete BEFORE trying to interact
    wait_for_angular(driver, timeout=30)

    # Extra buffer after Angular stabilizes - let options load
    time.sleep(1)
    print("  [Nav] Ready")
    return True

# ============================================================
# ⭐ Open mat-select and get options - simplified, proven selector
# ============================================================
def open_mat_select_and_get_options(driver, css_selector, timeout=15):
    """
    Find mat-select by CSS, click it, wait for options.
    Debug confirmed: mat-select[formcontrolname='officeId'] IS found correctly.
    The only issue was clicking before Angular was stable.
    """
    try:
        dropdown = driver.find_element(By.CSS_SELECTOR, css_selector)
    except Exception as e:
        print(f"    [Select] Element not found ({css_selector}): {e}")
        return None, []

    # Check not disabled
    if dropdown.get_attribute("aria-disabled") == "true":
        print(f"    [Select] Element is disabled: {css_selector}")
        return None, []

    # Scroll and click
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", dropdown)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", dropdown)
    print(f"    [Select] Clicked {css_selector}")

    # Wait for options panel to open and options to load
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.5)
        options = driver.find_elements(By.CSS_SELECTOR, "mat-option")
        visible = [o for o in options if o.is_displayed() and o.text.strip()]
        if visible:
            texts = [o.text.strip() for o in visible]
            print(f"    [Select] {len(visible)} options loaded: {texts}")
            return dropdown, visible

    print(f"    [Select] Timeout - no options appeared after clicking")
    # Close panel
    try:
        driver.execute_script("document.body.click();")
    except:
        pass
    return dropdown, []

def pick_option(options, target_text):
    target = target_text.strip().lower()
    for opt in options:
        if opt.text.strip().lower() == target:
            return opt
    for opt in options:
        txt = opt.text.strip().lower()
        if target in txt or txt in target:
            return opt
    return None

# ============================================================
# Wait for a mat-select to become enabled (not aria-disabled)
# ============================================================
def wait_for_enabled(driver, css_selector, timeout=20):
    print(f"    [Wait] Waiting for {css_selector} to be enabled...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            el = driver.find_element(By.CSS_SELECTOR, css_selector)
            if el.get_attribute("aria-disabled") != "true":
                print(f"    [Wait] Enabled after {round(time.time()-start,1)}s")
                return el
        except:
            pass
        time.sleep(0.5)
    print(f"    [Wait] Timeout - {css_selector} still disabled")
    return None

# ============================================================
# Steps
# ============================================================
def step1_select_center(driver, center_text):
    print("  [Step 1] Selecting center...")

    # Wait for Angular stability first - this is the key fix
    wait_for_angular(driver, timeout=20)

    dropdown, options = open_mat_select_and_get_options(
        driver, "mat-select[formcontrolname='officeId']", timeout=15
    )
    if not options:
        print("  [Step 1] FAILED - no options loaded")
        return False

    chosen = pick_option(options, center_text)
    if not chosen:
        available = [o.text.strip() for o in options]
        print(f"  [Step 1] FAILED - '{center_text}' not in: {available}")
        print(f"  [Step 1] TIP: Update config.py 'center' to one of: {available}")
        driver.execute_script("document.body.click();")
        return False

    js_click(driver, chosen)
    print(f"  [Step 1] Selected: {chosen.text.strip()}")

    # Wait for service level to become enabled
    el = wait_for_enabled(driver, "mat-select[formcontrolname='idServiceLevel']", timeout=15)
    if not el:
        print("  [Step 1] WARNING - service level did not activate")
        return False

    print("  [Step 1] Done")
    return True

def step2_select_service_level(driver, service_text):
    print("  [Step 2] Selecting service level...")

    _, options = open_mat_select_and_get_options(
        driver, "mat-select[formcontrolname='idServiceLevel']", timeout=15
    )
    if not options:
        print("  [Step 2] FAILED - no options loaded")
        return False

    chosen = pick_option(options, service_text)
    if not chosen:
        available = [o.text.strip() for o in options]
        print(f"  [Step 2] FAILED - '{service_text}' not in: {available}")
        print(f"  [Step 2] TIP: Update config.py 'service_level' to one of: {available}")
        driver.execute_script("document.body.click();")
        return False

    js_click(driver, chosen)
    print(f"  [Step 2] Selected: {chosen.text.strip()}")

    # Visa type dropdown - Angular assigns IDs dynamically
    # Wait a moment then find any enabled mat-select that's not center/service
    time.sleep(1)
    print("  [Step 2] Done")
    return True

def step3_select_visa_type(driver, visa_text):
    print("  [Step 3] Selecting visa type...")

    # The visa type dropdown has a dynamic mat-select ID.
    # Find any mat-select that is NOT officeId or idServiceLevel and is enabled.
    visa_selector = None
    for attempt in range(10):
        all_selects = driver.find_elements(By.CSS_SELECTOR, "mat-select")
        for s in all_selects:
            fc = s.get_attribute("formcontrolname") or ""
            el_id = s.get_attribute("id") or ""
            if fc in ("officeId", "idServiceLevel"):
                continue
            if s.get_attribute("aria-disabled") == "true":
                continue
            if s.is_displayed():
                visa_selector = s
                print(f"    [Step 3] Found visa dropdown: formcontrol={fc} id={el_id}")
                break
        if visa_selector:
            break
        time.sleep(1)

    if not visa_selector:
        print("  [Step 3] FAILED - visa type dropdown not found or still disabled")
        return False

    # Click and get options
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", visa_selector)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", visa_selector)
    print("  [Step 3] Clicked visa dropdown")

    start = time.time()
    while time.time() - start < 15:
        time.sleep(0.5)
        options = driver.find_elements(By.CSS_SELECTOR, "mat-option")
        visible = [o for o in options if o.is_displayed() and o.text.strip()]
        if visible:
            texts = [o.text.strip() for o in visible]
            print(f"    [Step 3] {len(visible)} options: {texts}")
            chosen = pick_option(visible, visa_text)
            if not chosen:
                print(f"  [Step 3] FAILED - '{visa_text}' not in: {texts}")
                print(f"  [Step 3] TIP: Update config.py 'visa_type' to one of: {texts}")
                driver.execute_script("document.body.click();")
                return False
            js_click(driver, chosen)
            print(f"  [Step 3] Selected: {chosen.text.strip()}")
            return True

    print("  [Step 3] FAILED - timeout waiting for visa options")
    return False

def step4_set_date(driver, date_value):
    print("  [Step 4] Setting date...")
    try:
        parts = date_value.split('/')
        formatted = f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{parts[2]}"
        date_input = WebDriverWait(driver, 15).until(
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
        """, date_input, formatted)
        print(f"  [Step 4] Date: {formatted}")
        time.sleep(0.5)
        return True
    except Exception as e:
        print(f"  [Step 4] FAILED: {e}")
        return False

def step5_set_destination(driver, destination):
    print("  [Step 5] Setting destination...")
    try:
        dest = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.XPATH, "//input[@formcontrolname='tripDestination']")
            )
        )
        dest.clear()
        dest.send_keys(destination)
        print(f"  [Step 5] Destination: {destination}")
        time.sleep(0.3)
        return True
    except Exception as e:
        print(f"  [Step 5] FAILED: {e}")
        return False

def step6_accept_terms(driver):
    print("  [Step 6] Accepting terms...")
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
    print(f"  [Step 6] Accepted {count} checkboxes")

# ============================================================
# Fill full form
# ============================================================
def fill_form_sequential(driver, data):
    print("\n  ===== Form Fill Start =====")
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.3)

    if not step1_select_center(driver, data["center"]):
        return False
    if not step2_select_service_level(driver, data["service_level"]):
        return False
    if not step3_select_visa_type(driver, data["visa_type"]):
        return False
    if not step4_set_date(driver, data["travel_date"]):
        return False
    if not step5_set_destination(driver, data["destination"]):
        return False
    step6_accept_terms(driver)

    print("  ===== Form Fill Done ✅ =====\n")
    return True

# ============================================================
# Check slots
# ============================================================
def check_slots(driver):
    try:
        check_btn = None
        for xpath in [
            "//button[contains(., 'افحص الاماكن المتاحة')]",
            "//button[contains(., 'افحص الأماكن المتاحة')]",
            "//button[contains(., 'الاماكن المتاحة')]",
            "//button[contains(., 'Check availability')]",
            "//button[contains(., 'Check Availability')]",
            "//button[@type='submit']",
        ]:
            try:
                check_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                break
            except:
                continue

        if not check_btn:
            print("  [Check] Submit button not found")
            return False, None

        js_click(driver, check_btn)
        print("  [Check] Clicked submit")
        time.sleep(4)

        page = driver.page_source.lower()
        for kw in ["no available", "not available", "no slots",
                   "لا توجد مواعيد", "لا يوجد", "لا توجد أماكن"]:
            if kw in page:
                print("  [Check] No slots")
                return False, None

        for sel in [".available-day", "[class*='available']",
                    "[class*='slot']", "[class*='calendar']"]:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            slots = [e.text for e in els if e.text.strip()]
            if slots:
                print(f"  [Check] ✅ SLOTS: {slots[:5]}")
                return True, slots[:5]

        return False, None

    except Exception as e:
        print(f"  [Check] Error: {e}")
        return False, None

# ============================================================
# Main loop
# ============================================================
def run_forever(driver, account):
    email = account["email"]
    data = account["data"]
    print(f"\n[{email}] Started - interval: {REFRESH_INTERVAL}s")

    attempt = 0
    fail_count = 0

    while not stop_flag.is_set():
        attempt += 1
        try:
            _ = driver.current_url
        except:
            print(f"[{email}] Browser lost")
            notify_error(account, "Browser closed unexpectedly")
            break

        try:
            if not go_to_appointment_page(driver):
                fail_count += 1
                print(f"[{email}] Nav failed #{fail_count}")
                if fail_count >= 3:
                    notify_error(account, f"Navigation failed {fail_count}x")
                    fail_count = 0
                    login(driver, email, account["password"])
                time.sleep(5)
                continue

            success = fill_form_sequential(driver, data)

            if not success:
                fail_count += 1
                print(f"[{email}] Form failed #{fail_count}")
                if fail_count >= 5:
                    notify_error(account, f"Form fill failed {fail_count}x")
                    fail_count = 0
                    login(driver, email, account["password"])
                time.sleep(3)
                continue

            fail_count = 0
            has_slots, slots = check_slots(driver)
            if has_slots:
                notify_success(account, slots)
                print(f"[{email}] ✅✅✅ SLOTS FOUND! Attempt #{attempt}")
                stop_flag.set()
                return True

            if attempt % 5 == 0:
                print(f"[{email}] Attempt #{attempt}: searching...")

        except WebDriverException as e:
            err = str(e).lower()
            if "invalid session" in err or "disconnected" in err:
                print(f"[{email}] Browser disconnected")
                notify_error(account, "Browser disconnected")
                break
            print(f"[{email}] WebDriver error: {e}")
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
        print(f"\n{'='*50}")
        print(f"Starting: {email}")
        print(f"{'='*50}")
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
    ║     Almaviva Booking Bot v7.6              ║
    ║     (Angular stability fix)                ║
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
        print("\n⚠️ Stopped manually")
        stop_flag.set()

    print("\nBot finished.")

if __name__ == "__main__":
    main()