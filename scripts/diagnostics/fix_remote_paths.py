import os
import django
import sys

# Setup Django
sys.path.append('/home/prodisyn_innovations/SafeLensAI/database-api')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from apps.api.models import Incident
from django.db import transaction

def fix_paths():
    old_base = "/home/prodisyn-innovations/tilak-reference/P004-SafeLensAI-Demo/SafeLensAI/"
    new_base = "/home/prodisyn_innovations/SafeLensAI/"
    
    print(f"--- Fixing paths in Database ---")
    print(f"Searching for incidents starting with: {old_base}")
    
    with transaction.atomic():
        incidents = Incident.objects.filter(image_url__icontains="prodisyn-innovations")
        count = incidents.count()
        print(f"Found {count} incidents to update.")
        
        for inc in incidents:
            if inc.image_url:
                inc.image_url = inc.image_url.replace(old_base, new_base)
            if inc.video_url:
                inc.video_url = inc.video_url.replace(old_base, new_base)
            inc.save()
            
    print(f"Update complete. {count} records modified.")

if __name__ == "__main__":
    fix_paths()
