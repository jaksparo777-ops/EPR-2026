import sys, time, os
import django
sys.path.insert(0, '/Users/kizzzz/erp_project/3_erp_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.conf import settings

User = get_user_model()
user = User.objects.filter(is_superuser=True).first() or User.objects.first()

session = SessionStore()
session[django.contrib.auth.SESSION_KEY] = user._meta.pk.value_to_string(user)
session[django.contrib.auth.BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'
session[django.contrib.auth.HASH_SESSION_KEY] = user.get_session_auth_hash()
session.save()

session_key = session.session_key
print('Generated Session Key:', session_key, 'for user:', user.username)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

options = Options()
options.binary_location = '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

driver = webdriver.Chrome(options=options)

try:
    driver.get('http://127.0.0.1:8000/404/') # load domain to set cookie
    driver.add_cookie({
        'name': settings.SESSION_COOKIE_NAME,
        'value': session_key,
        'path': '/',
        'domain': '127.0.0.1'
    })
    
    print('\nNavigating to http://127.0.0.1:8000/ledger/?month=2026-08 in BRAVE...')
    driver.get('http://127.0.0.1:8000/ledger/?month=2026-08')
    time.sleep(2)
    print('Current URL:', driver.current_url)

    print('\nChecking initial browser logs in BRAVE:')
    logs = driver.get_log('browser')
    print(f'Total log entries: {len(logs)}')
    for entry in logs:
        print('  [Console Log]', entry['level'], entry['message'])

    btn_jw = driver.find_element(By.ID, 'btn-jw')
    btn_staff = driver.find_element(By.ID, 'btn-staff')
    btn_sheet = driver.find_element(By.ID, 'btn-sheet')

    print('\nTesting Tab 2 (Job Work Ledger):')
    print('  Clicking btn-jw...')
    btn_jw.click()
    time.sleep(1)
    
    sec_jw = driver.find_element(By.ID, 'section-jw')
    sec_staff = driver.find_element(By.ID, 'section-staff')
    sec_sheet = driver.find_element(By.ID, 'section-sheet')
    
    print('  section-jw displayed:', sec_jw.is_displayed())
    print('  section-staff displayed:', sec_staff.is_displayed())
    print('  section-sheet displayed:', sec_sheet.is_displayed())

    print('\nTesting Tab 3 (Monthly Attendance Sheet):')
    print('  Clicking btn-sheet...')
    btn_sheet.click()
    time.sleep(1)
    
    print('  section-sheet displayed:', sec_sheet.is_displayed())
    print('  section-jw displayed:', sec_jw.is_displayed())
    print('  section-staff displayed:', sec_staff.is_displayed())

    print('\nBrowser Console Logs after tab switching in BRAVE:')
    logs2 = driver.get_log('browser')
    print(f'Total log entries: {len(logs2)}')
    for entry in logs2:
        print('  [Console Log]', entry['level'], entry['message'])

finally:
    driver.quit()
