# Worker Safety API - Complete Development Guide

## Table of Contents
1. [User Requirements](#user-requirements)
2. [System Architecture](#system-architecture)
3. [Development Journey](#development-journey)
4. [API Implementation Details](#api-implementation-details)
5. [Recent Enhancements](#recent-enhancements)
6. [Code Walkthrough](#code-walkthrough)

---

## User Requirements

### Initial Requirements
The Worker Safety System needed a Django REST API to:
1. **Expose existing PostgreSQL database** containing worker safety events
2. **Provide event data** to a React-based dashboard UI
3. **Support filtering** by date and incident type
4. **Deliver statistical summaries** for reporting
5. **Generate time-series data** for visualization charts

### Evolution: Detailed PPE Violations
The system was later enhanced to:
1. **Show specific missing PPE items** (helmet, vest, gloves, glasses) instead of generic "PPE Violation"
2. **Provide individual incident counts** (Fall, Intrusion, Helmet, Vest) for charts
3. **Support multi-color visualizations** with distinct colors for each incident type
4. **Enable filtering by specific PPE violations**

---

## System Architecture

### Technology Stack
- **Backend**: Django 4.2+ with Django REST Framework
- **Database**: PostgreSQL (existing database from detection system)
- **Frontend**: React + TypeScript with Vite
- **Charting**: Recharts library

### Database Design
The system uses the following key tables:

```
events
├── event_id (PK)
├── camera_id (FK → camera)
├── event_type (VARCHAR: FALL_DETECTED, PPE_VIOLATION, INTRUSION)
└── timestamp

events_detections
├── detection_id (PK)
├── event_id (FK → events)
├── model_id (FK → detection_model)
├── detection_type (VARCHAR)
├── detection_value (VARCHAR: "No Helmet", "No Vest", etc.)
└── detection_details (JSONB: structured detection data)

frames
├── frame_id (PK)
└── storage_path (VARCHAR: path to image file)

event_media_map
├── event_id (FK)
├── media_type (VARCHAR: "FRAME", "CLIP")
└── media_id (INT: references frame_id or clip_id)
```

### API Endpoints Structure

```
/api/
├── events/              # Standard event CRUD
├── cameras/             # Camera management
├── decisions/           # Access decisions
└── overview/            # Dashboard-specific endpoints
    ├── events/          # Filtered event list
    ├── summary/         # Statistical summary
    └── graph/           # Time-series data
```

---

## Development Journey

### Phase 1: Basic API Setup (Initial Development)

#### Step 1: Project Initialization
```bash
# Create Django project
django-admin startproject safelensai
cd safelensai-backend-api-server
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install django djangorestframework psycopg2-binary django-cors-headers
```

#### Step 2: Database Connection
**File: `safelensai/settings.py`**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'worker_safety_db',
        'USER': 'safelens_user',
        'PASSWORD': '<DB_PASSWORD>',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

#### Step 3: Model Creation (Read-Only)
**File: `api/models.py`**

Created Django models mapped to existing database tables:
```python
class Event(models.Model):
    event_id = models.AutoField(primary_key=True)
    camera = models.ForeignKey(Camera, models.DO_NOTHING)
    event_type = models.CharField(max_length=100)
    timestamp = models.DateTimeField()
    
    class Meta:
        managed = False  # Don't let Django modify the database
        db_table = 'events'
```

**Why `managed = False`?**
- The database already exists from the detection system
- Django should only READ from the database, not modify schema
- Prevents accidental migrations that could break the detection system

#### Step 4: Basic Serializers
**File: `api/serializers.py`**
```python
class EventSerializer(serializers.ModelSerializer):
    camera = CameraSerializer(read_only=True)
    detections = EventDetectionSerializer(many=True, read_only=True)
    
    class Meta:
        model = Event
        fields = ['event_id', 'event_type', 'timestamp', 'camera', 'detections']
```

#### Step 5: ViewSets for CRUD
**File: `api/views.py`**
```python
class EventViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only API for safety events"""
    queryset = Event.objects.all().order_by('-timestamp')
    serializer_class = EventSerializer
```

**Why ReadOnlyModelViewSet?**
- Events are created by the detection system, not the API
- API should only provide read access for the dashboard
- Prevents accidental data modification through API

---

### Phase 2: Dashboard-Specific Endpoints

#### Overview Requirements
The React dashboard needed:
1. **Event list** with images, filterable by date and type
2. **Summary statistics** showing counts and percentages
3. **Graph data** aggregated by time (hourly, daily)

#### Implementation: OverviewViewSet

**File: `api/views.py`** (lines 32-160)

##### Endpoint 1: `/api/overview/events/`
```python
@action(detail=False, methods=['get'])
def events(self, request):
    """Filter events by date and type"""
    date_str = request.query_params.get('date')
    event_type = request.query_params.get('type')
    
    queryset = Event.objects.all().order_by('-timestamp')
    
    if date_str:
        search_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        queryset = queryset.filter(timestamp__date=search_date)
    
    if event_type:
        queryset = queryset.filter(event_type__iexact=event_type)
    
    serializer = OverviewEventSerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)
```

**Design Decisions:**
- Query parameters for filtering (RESTful design)
- Case-insensitive type matching (`iexact`)
- Pass request context to serializer for building absolute URLs

##### Endpoint 2: `/api/overview/summary/`
```python
@action(detail=False, methods=['get'])
def summary(self, request):
    """Calculate statistics for dashboard cards"""
    queryset = Event.objects.all()
    # Apply date/type filters...
    
    total_events = queryset.count()
    fall_count = queryset.filter(event_type__iexact='FALL_DETECTED').count()
    # Calculate percentages...
    
    return Response({
        'total_events': total_events,
        'fall_count': fall_count,
        # ... more statistics
    })
```

##### Endpoint 3: `/api/overview/graph/`
```python
@action(detail=False, methods=['get'])
def graph(self, request):
    """Aggregate events by time period"""
    time_range = request.query_params.get('time_range', 'today')
    
    if time_range == 'today':
        # Aggregate by hour
        stats = queryset.annotate(
            hour=TruncHour('timestamp')
        ).values('hour').annotate(
            count=Count('event_id')
        ).order_by('hour')
        
        # Fill in missing hours with 0
        hours = {start_time + timedelta(hours=i): 0 for i in range(24)}
        for item in stats:
            hours[item['hour']] = item['count']
```

**Key Concepts:**
- **TruncHour/TruncDay**: Django ORM functions to group by time period
- **Zero-filling**: Ensure all time slots appear in chart (even if no events)
- **Format labels**: "10:00" for hours, "Mon" for days, "Jan 01" for dates

---

### Phase 3: Image URL Integration

#### Challenge
Events need associated images from the `frames` table, linked through `event_media_map`.

#### Solution: SerializerMethodField
**File: `api/serializers.py`** (lines 38-65)

```python
class OverviewEventSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    
    def get_image_url(self, obj):
        """Build full URL to event image"""
        try:
            # Find frame associated with this event
            media_map = EventMediaMap.objects.filter(
                event_id=obj.event_id, 
                media_type='FRAME'
            ).first()
            
            if media_map:
                frame = Frame.objects.filter(frame_id=media_map.media_id).first()
                if frame and frame.storage_path:
                    # Build absolute URL
                    request = self.context.get('request')
                    return request.build_absolute_uri(
                        settings.MEDIA_URL + frame.storage_path
                    )
        except Exception:
            return None
```

**Why SerializerMethodField?**
- Custom logic needed to traverse multiple tables
- Can't use simple ForeignKey relationships (polymorphic relationship)
- Need request context to build absolute URLs

**MEDIA Configuration:**
```python
# settings.py
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# urls.py
from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

---

## Phase 4: Enhanced PPE Violation Details

### User Requirement Evolution
**Original**: Events showed as generic "PPE Violation"
**New Requirement**: Show WHICH PPE items are missing (helmet, vest, etc.)

### Implementation Approach

#### Step 1: Analyze Detection Data Structure
Examined the `events_detections` table:
- `detection_value` contains strings like "No Helmet", "Missing Vest"
- `detection_details` JSONB may contain structured data

#### Step 2: Add missing_items Field
**File: `api/serializers.py`** (lines 38-131)

```python
class OverviewEventSerializer(serializers.ModelSerializer):
    missing_items = serializers.SerializerMethodField()
    
    class Meta:
        fields = ['event_id', 'event_type', 'timestamp', 'location', 
                  'image_url', 'missing_items']
    
    def get_missing_items(self, obj):
        """Extract specific PPE violations"""
        # Only process PPE events
        if 'PPE' not in obj.event_type.upper():
            return []
        
        missing_items = []
        detections = EventDetection.objects.filter(event_id=obj.event_id)
        
        for detection in detections:
            # Parse detection_value
            if detection.detection_value:
                value_lower = detection.detection_value.lower()
                if 'helmet' in value_lower or 'hardhat' in value_lower:
                    missing_items.append('helmet')
                if 'vest' in value_lower:
                    missing_items.append('vest')
                # ... check for gloves, glasses
            
            # Also check JSONB detection_details
            if detection.detection_details:
                # Handle various JSONB structures
                if 'missing_ppe' in details:
                    items = details['missing_ppe']
                    missing_items.extend(items)
        
        return list(set(missing_items))  # Remove duplicates
```

**Why Multiple Parsing Strategies?**
- Detection systems may store data in different formats
- Need to handle both legacy and new data structures
- Robustness: Try multiple methods to extract information

#### Step 3: Update Summary for Individual Counts
**File: `api/views.py`** (lines 61-143)

```python
def summary(self, request):
    # Get basic counts
    fall_count = queryset.filter(event_type__iexact='FALL_DETECTED').count()
    intrusion_count = queryset.filter(event_type__iexact='INTRUSION').count()
    
    # Analyze PPE events for specific items
    helmet_count = 0
    vest_count = 0
    
    ppe_events = queryset.filter(event_type__icontains='PPE')
    for event in ppe_events:
        detections = EventDetection.objects.filter(event_id=event.event_id)
        
        for detection in detections:
            if detection.detection_value:
                value_lower = detection.detection_value.lower()
                if 'helmet' in value_lower:
                    helmet_count += 1
                    break  # Count event once
                elif 'vest' in value_lower:
                    vest_count += 1
                    break
    
    return Response({
        'total_events': total_events,
        'fall_count': fall_count,
        'intrusion_count': intrusion_count,
        'helmet_count': helmet_count,
        'vest_count': vest_count,
        # ...
    })
```

**Performance Consideration:**
- This requires iterating through events in Python
- For large datasets, consider creating a database view or materialized view
- Trade-off: Simplicity vs Performance

#### Step 4: Multi-Type Graph Data
**File: `api/views.py`** (lines 145-322)

Created two response formats:

**Format 1: Grouped Data (for all-types view)**
```python
def _get_grouped_graph_data(self, queryset, time_range, now):
    """Returns data with separate counts for each type"""
    # Initialize time periods
    hours = {
        start_time + timedelta(hours=i): {
            'fall': 0, 
            'intrusion': 0, 
            'helmet': 0, 
            'vest': 0
        } for i in range(24)
    }
    
    # Categorize each event
    for event in queryset:
        hour_key = event.timestamp.replace(minute=0, second=0)
        if 'FALL' in event.event_type.upper():
            hours[hour_key]['fall'] += 1
        elif 'INTRUSION' in event.event_type.upper():
            hours[hour_key]['intrusion'] += 1
        elif 'PPE' in event.event_type.upper():
            # Check detections for specific PPE type
            detections = EventDetection.objects.filter(event_id=event.event_id)
            # Categorize as helmet or vest...
    
    return [
        {
            'label': '10:00',
            'fall': 5,
            'intrusion': 3,
            'helmet': 8,
            'vest': 6
        }
    ]
```

**Format 2: Simple Data (for filtered view)**
```python
def _get_simple_graph_data(self, queryset, time_range, now):
    """Returns simple count format"""
    return [
        {'label': '10:00', 'count': 16},
        {'label': '11:00', 'count': 23}
    ]
```

**Why Two Formats?**
- Multi-color stacked chart needs separate counts
- Single-color chart needs simple count
- Backend adapts response based on filter selection

---

## Code Walkthrough

### Complete File Structure

```
Worker-Safety-API/
├── api/
│   ├── models.py          # Database models (managed=False)
│   ├── serializers.py     # JSON serialization + custom fields
│   ├── views.py           # API endpoints and business logic
│   └── urls.py            # URL routing
├── safelensai/
│   ├── settings.py        # Django configuration
│   └── urls.py            # Root URL configuration
├── media/                 # Served image files
├── requirements.txt       # Python dependencies
└── manage.py              # Django management script
```

### Key Code Sections Explained

#### 1. models.py - Data Layer
```python
# Line 79-87: Core Event Model
class Event(models.Model):
    event_id = models.AutoField(primary_key=True)
    camera = models.ForeignKey(Camera, models.DO_NOTHING, db_column='camera_id')
    event_type = models.CharField(max_length=100)
    timestamp = models.DateTimeField()
    
    class Meta:
        managed = False  # READ-ONLY: Don't modify database
        db_table = 'events'
```

#### 2. serializers.py - Transformation Layer
```python
# Lines 38-131: Enhanced Event Serializer
class OverviewEventSerializer(serializers.ModelSerializer):
    # CUSTOM FIELDS (not in database)
    location = serializers.CharField(source='camera.location')
    image_url = serializers.SerializerMethodField()
    missing_items = serializers.SerializerMethodField()
    
    # METHOD 1: Image URL Builder
    def get_image_url(self, obj):
        # Traverse: event → event_media_map → frames
        # Build: http://localhost:8000/media/frames/image.jpg
    
    # METHOD 2: PPE Item Extractor  
    def get_missing_items(self, obj):
        # Parse: events_detections table
        # Extract: specific PPE violations
        # Return: ["helmet", "vest", "gloves"]
```

#### 3. views.py - Business Logic Layer
```python
# Lines 32-59: Event List with Filters
@action(detail=False, methods=['get'])
def events(self, request):
    # 1. Start with all events
    queryset = Event.objects.all()
    
    # 2. Apply date filter if provided
    if date_str:
        queryset = queryset.filter(timestamp__date=search_date)
    
    # 3. Apply type filter if provided
    if event_type:
        queryset = queryset.filter(event_type__iexact=event_type)
    
    # 4. Serialize and return
    serializer = OverviewEventSerializer(queryset, many=True)
    return Response(serializer.data)

# Lines 61-143: Statistical Summary
@action(detail=False, methods=['get'])
def summary(self, request):
    # 1. Count events by type
    # 2. Analyze PPE events for specific items
    # 3. Calculate percentages
    # 4. Return structured summary

# Lines 145-322: Time-Series Graph Data
@action(detail=False, methods=['get'])
def graph(self, request):
    # Route to appropriate handler
    if event_type and event_type != 'all':
        return self._get_simple_graph_data(...)  # Single type
    else:
        return self._get_grouped_graph_data(...)  # Multi-type
```

---

## How Each API Was Created

### `/api/overview/events/` - Event List API

**Purpose**: Provide filterable list of events with images for dashboard cards

**Development Steps:**
1. Created `OverviewEventSerializer` extending `EventSerializer`
2. Added `location` field using `source='camera.location'`
3. Added `image_url` using `SerializerMethodField` with custom logic
4. Added `missing_items` for PPE violations
5. Created `events` action in `OverviewViewSet`
6. Implemented query parameter filtering
7. Registered viewset in `urls.py`

**Files Modified:**
- `api/serializers.py` (lines 38-131)
- `api/views.py` (lines 37-59)
- `api/urls.py` (added overview router)

---

### `/api/overview/summary/` - Statistics API

**Purpose**: Provide counts and percentages for dashboard KPI cards

**Development Steps:**
1. Created `summary` action method
2. Implemented date filtering
3. Added individual type counting (fall, intrusion, PPE)
4. Enhanced with specific PPE item counts (helmet, vest)
5. Added percentage calculations
6. Structured response with all metrics

**Files Modified:**
- `api/views.py` (lines 61-143)

**Optimization Tips:**
```python
# Instead of multiple queries:
fall_count = queryset.filter(event_type='FALL').count()
intrusion_count = queryset.filter(event_type='INTRUSION').count()

# Could use aggregate with conditional expressions:
from django.db.models import Count, Q
counts = queryset.aggregate(
    fall=Count('event_id', filter=Q(event_type='FALL_DETECTED')),
    intrusion=Count('event_id', filter=Q(event_type='INTRUSION'))
)
```

---

### `/api/overview/graph/` - Time-Series API

**Purpose**: Provide aggregated data for line/bar charts

**Development Steps:**
1. Created `graph` action with time_range parameter
2. Implemented hour/day/month aggregation using Django ORM
3. Added zero-filling for complete time series
4. Enhanced with multi-type breakdown
5. Split into two methods for different response formats
6. Added dynamic routing based on filter selection

**Files Modified:**
- `api/views.py` (lines 145-322)

**Advanced Django ORM:**
```python
# Time truncation and aggregation
from django.db.models.functions import TruncHour

stats = Event.objects.filter(
    timestamp__gte=start_time
).annotate(
    hour=TruncHour('timestamp')  # Group by hour
).values('hour').annotate(
    count=Count('event_id')  # Count events per hour
).order_by('hour')
```

---

## Testing the APIs

### Manual Testing with curl

```bash
# Test 1: Get today's events
curl "http://localhost:8000/api/overview/events/?date=2026-02-09"

# Test 2: Get PPE violations only
curl "http://localhost:8000/api/overview/events/?type=PPE_VIOLATION"

# Test 3: Get summary statistics
curl "http://localhost:8000/api/overview/summary/"

# Test 4: Get graph data for today
curl "http://localhost:8000/api/overview/graph/?time_range=today"

# Test 5: Get filtered graph data
curl "http://localhost:8000/api/overview/graph/?time_range=week&type=FALL_DETECTED"
```

### Testing with Python

```python
import requests

# Test missing_items field
response = requests.get(
    'http://localhost:8000/api/overview/events/',
    params={'type': 'PPE_VIOLATION'}
)
events = response.json()
for event in events:
    print(f"Event {event['event_id']}: Missing {event['missing_items']}")

# Test grouped graph data
response = requests.get(
    'http://localhost:8000/api/overview/graph/',
    params={'time_range': 'today'}
)
data = response.json()
print(f"First hour has {data[0]['fall']} falls, {data[0]['helmet']} helmet violations")
```

---

## Lessons Learned & Best Practices

### 1. Database Integration
✅ **Do**: Use `managed = False` for existing databases
✅ **Do**: Inspect database schema before creating models
❌ **Don't**: Run migrations on external databases

### 2. API Design
✅ **Do**: Use query parameters for filtering (RESTful)
✅ **Do**: Provide clear, predictable response structures
✅ **Do**: Version your API if structure might change
❌ **Don't**: Put too much logic in serializers

### 3. Performance
✅ **Do**: Use Django ORM aggregation when possible
✅ **Do**: Consider database indexes on filtered fields
⚠️ **Consider**: Caching for expensive calculations
❌ **Don't**: Loop through large datasets in Python

### 4. Error Handling
```python
# Good: Try-except with graceful degradation
def get_image_url(self, obj):
    try:
        # Complex logic
        return url
    except Exception:
        return None  # Fail gracefully

# Bad: Let exceptions crash the API
def get_image_url(self, obj):
    media_map = EventMediaMap.objects.get(...)  # May raise DoesNotExist
```

---

## Future Enhancements

### Potential Improvements
1. **WebSocket Support**: Real-time event streaming
2. **Pagination**: Handle thousands of events efficiently
3. **Caching**: Redis cache for summary statistics
4. **Batch Endpoints**: Get multiple resources in one request
5. **GraphQL**: Alternative to REST for flexible queries

### Performance Optimization
```python
# Current: N queries for missing_items
for event in ppe_events:
    detections = EventDetection.objects.filter(event_id=event.event_id)

# Better: Prefetch related detections
ppe_events = queryset.filter(event_type__icontains='PPE').prefetch_related(
    'eventdetection_set'
)
for event in ppe_events:
    detections = event.eventdetection_set.all()  # No DB query!
```

---

## Conclusion

This API was developed iteratively:
1. **Phase 1**: Basic CRUD endpoints
2. **Phase 2**: Dashboard-specific endpoints with filtering
3. **Phase 3**: Image integration via media files
4. **Phase 4**: Enhanced PPE details with multi-type breakdown

The design prioritizes:
- **Simplicity**: RESTful design, clear endpoint purposes
- **Flexibility**: Query parameters for various use cases
- **Robustness**: Graceful error handling, null safety
- **Performance**: Django ORM optimization where possible

Every API endpoint serves a specific dashboard need, and the response structures are optimized for frontend consumption.
