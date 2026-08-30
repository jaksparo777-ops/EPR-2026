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
print('Generated Session Key:', session_key)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

options = Options()
options.binary_location = '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--window-size=1400,900')

driver = webdriver.Chrome(options=options)

artifact_dir = '/Users/kizzzz/.gemini/antigravity-ide/brain/e3cb0f84-faa7-4c28-8c54-89ad26be7509'

try:
    driver.get('http://127.0.0.1:8000/404/')
    driver.add_cookie({
        'name': settings.SESSION_COOKIE_NAME,
        'value': session_key,
        'path': '/',
        'domain': '127.0.0.1'
    })

    urls_to_test = [
        ('tab_jw', 'http://127.0.0.1:8000/ledger/?tab=jw&month=2026-08'),
        ('tab_sheet', 'http://127.0.0.1:8000/ledger/?tab=sheet&month=2026-08'),
        ('drawer_payment', 'http://127.0.0.1:8000/ledger/?tab=staff&drawer=payment&month=2026-08'),
    ]

    for name, url in urls_to_test:
        print(f'\nNavigating to {url}...')
        driver.get(url)
        time.sleep(2)
        shot_path = os.path.join(artifact_dir, f'screenshot_{name}.png')
        driver.save_screenshot(shot_path)
        print(f'Saved screenshot for {name} to {shot_path}')

finally:
    driver.quit()
