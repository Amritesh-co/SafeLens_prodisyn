import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

import traceback
try:
    from safelensai import urls
    print("Imports OK")
except Exception as e:
    print(traceback.format_exc())
