"""
URL configuration for safelensai project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from apps.api.views import OpsDashboardView
from apps.api.assistant.views import AssistantLoginView, AssistantLogoutView, AssistantPlaygroundView
from django.shortcuts import redirect
from django.http import JsonResponse

def home(request):
    return redirect("/admin/")

def health(request):
    return JsonResponse({
        "status": "ok",
        "service": "SafeLens API"
    })
    
urlpatterns = [
    path("", home),
    path('admin/', admin.site.urls),
    path("health/", health),
    path('api/', include('apps.api.urls')),
    path('ops/notifications', OpsDashboardView.as_view(), name='ops-notifications-no-slash'),
    path('ops/notifications/', OpsDashboardView.as_view(), name='ops-notifications'),
    # AI assistant dev playground (404 unless DEBUG=True)
    path('assistant/', AssistantPlaygroundView.as_view(), name='assistant-playground'),
    path('assistant/login/', AssistantLoginView.as_view(), name='assistant-login'),
    path('assistant/logout/', AssistantLogoutView.as_view(), name='assistant-logout'),
]

import os
import urllib.parse
from django.http import JsonResponse, FileResponse, Http404

def serve_absolute_media(request, path):
    """
    Serves files from absolute filesystem paths OR relative storage paths.
    Automatically handles path mismatches between local and remote environments.
    """
    # 1. Unquote URL encoding (%20 -> space)
    normalized_path = urllib.parse.unquote(path)
    
    # 2. Normalize prefix (strip /media/ if present)
    internal_path = normalized_path
    if internal_path.startswith('media/'):
        internal_path = internal_path[6:]
    elif internal_path.startswith('/media/'):
        internal_path = internal_path[7:]
    
    # 3. Determine potential full paths
    potential_paths = []
    
    # A. If it's already an absolute path, try it first
    if internal_path.startswith('/'):
        potential_paths.append(internal_path)
    
    # B. Try resolving relative to current SYSTEM_STORAGE_DIR
    storage_base = os.environ.get('SYSTEM_STORAGE_DIR')
    if not storage_base:
        storage_base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'storage'))
    
    alt_storage_bases = [
        item.strip()
        for item in os.environ.get('SYSTEM_STORAGE_ALT_DIRS', '').split(',')
        if item.strip()
    ]
    
    # C. RECOVERY LOGIC - Unified approach
    suffix = None
    if 'storage/' in internal_path:
        suffix = internal_path.split('storage/')[1]
    elif 'incidents/' in internal_path:
        suffix = "incidents/" + internal_path.split('incidents/')[1]
    
    if suffix:
        suffix = suffix.lstrip('/')
        potential_paths.append(os.path.abspath(os.path.join(storage_base, suffix)))
        for alt in alt_storage_bases:
            potential_paths.append(os.path.abspath(os.path.join(alt, suffix)))
    
    # D. Fallback: Search by filename in likely folders
    filename_only = os.path.basename(internal_path)
    if filename_only and len(filename_only) > 5:
        hotspots = [
            "incidents/images/ppe/Hard-hat",
            "incidents/images/ppe/Safety-vest",
            "incidents/images/fall",
            "incidents/images/intrusion",
            "incidents/videos"
        ]
        for sub in hotspots:
            potential_paths.append(os.path.join(storage_base, sub, filename_only))
            for alt in alt_storage_bases:
               potential_paths.append(os.path.join(alt, sub, filename_only))

    # 4. Find the first existing file
    full_path = None
    # Remove duplicates but preserve order
    unique_potential = []
    for p in potential_paths:
        if p not in unique_potential: unique_potential.append(p)

    for p in unique_potential:
        if os.path.isfile(p):
            full_path = p
            break
        # Handle historical storage paths with underscore/hyphen spelling differences.
        fuzzy_p = p.replace('prodisyn_innovations', 'prodisyn-innovations').replace('prodisyn-innovations', 'prodisyn_innovations')
        if fuzzy_p != p and os.path.isfile(fuzzy_p):
            full_path = fuzzy_p
            break
            
    if full_path:
        document_root = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        
        from django.views.static import serve
        response = serve(request, filename, document_root=document_root)
        
        # Explicit CORS for media - Critical for cross-domain playback
        response["Access-Control-Allow-Origin"] = "*"
        return response
    else:
        # Debug 404
        return JsonResponse({
            "error": "Image file not found on disk after comprehensive search",
            "tried_paths": unique_potential[:7],
            "storage_base_used": storage_base,
            "original_param": path
        }, status=404)

urlpatterns += [
    re_path(r'^(?P<path>.*)$', serve_absolute_media),
]
