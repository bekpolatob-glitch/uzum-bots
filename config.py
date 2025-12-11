import os

# Place any site-specific urls or overrides here.
# You can modify CATEGORY_URLS to include the sections of Uzum you want monitored.

CATEGORY_URLS = os.getenv('UZUM_CATEGORY_URLS')
if CATEGORY_URLS:
    CATEGORY_URLS = [u.strip() for u in CATEGORY_URLS.split(',') if u.strip()]
else:
    CATEGORY_URLS = ['https://uzum.uz/']
