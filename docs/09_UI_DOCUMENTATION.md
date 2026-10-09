# Worker Safety UI - Complete Documentation

## Overview

The Worker Safety UI is a modern web application built with React and TypeScript that provides real-time monitoring and analysis of workplace safety incidents. The system integrates with a Django REST API backend to fetch and display safety events, statistics, and trends.

---

## 📸 Quick Visual Reference

Below are the key UI components of the Worker Safety system. Click on any image for details.

### Dashboard with All Dropdowns Open

![UI with Dropdowns](/home/rajanikanth/.gemini/antigravity/brain/48f0fa5b-d958-438f-8e6e-a705de5f0fd7/ui_with_dropdowns_open_1770713730562.png)

**Shows**: All interactive dropdown menus in their expanded state - Incident Type, Date Picker, Time Range, and Chart Type filters.

### Incident Cards Grid

![Incident Cards](/home/rajanikanth/.gemini/antigravity/brain/48f0fa5b-d958-438f-8e6e-a705de5f0fd7/detailed_incident_cards_1770713748520.png)

**Shows**: 6 incident cards displaying Event ID, Time, Location, Type, and thumbnail images with pagination controls.

### Charts and Statistics

![Charts Section](/home/rajanikanth/.gemini/antigravity/brain/48f0fa5b-d958-438f-8e6e-a705de5f0fd7/charts_section_detailed_1770713780653.png)

**Shows**: Line chart (Incidents Trend), Donut chart (Incident Overview with percentages), and Bar chart (Incidents Over Time).

### Sidebar Navigation

![Sidebar](/home/rajanikanth/.gemini/antigravity/brain/48f0fa5b-d958-438f-8e6e-a705de5f0fd7/sidebar_component_detail_1770713840445.png)

**Shows**: ProDiSyn branding, user profile (Rajanikanth - Administrator), navigation menu with 4 pages, and logout button.

---

## UI Layout & Structure

### Main Layout

The application uses a **sidebar + content area** layout:

- **Left Sidebar** (Fixed width: 256px)
  - Company branding
  - User profile
  - Navigation menu
  - Footer information
  
- **Main Content Area** (Flexible width)
  - Dynamic page content
  - Scrollable area

---

## 1. Sidebar Component

### Visual Elements

#### Company Logo Section
- **ProDiSyn Logo**: Gradient badge (blue to orange) with checkmark icon
- **Company Name**: "ProDiSyn Innovations"
- **Tagline**: "Intelligence Embedded • Solutions Engineered"

#### User Profile Section
- **User Avatar**: Circular badge with initial "R"
- **Display Name**: "Rajanikanth"
- **Role**: "Administrator"
- **Logout Button**: Icon button with hover effect
  - **Action**: Redirects to login page
  - **Icon**: Logout icon (red on hover)

#### Navigation Menu

The sidebar contains 4 navigation items, each with an icon and label:

| Icon | Label | Page ID | Status |
|------|-------|---------|---------|
| 📊 | Overview | `overview` | Active |
| ⚠️ | Incidents | `incidents` | Under Construction |
| 👥 | User Management | `users` | Under Construction |
| ⚙️ | Settings | `settings` | Under Construction |

**Active State**: Blue background with bold text
**Inactive State**: Gray text with hover effect

#### Footer
- Version information: "Safety Compliance v1.0"

### No API Interaction
The sidebar is purely a UI navigation component with no direct API calls.

---

## 2. Overview Dashboard (Main Page)

This is the primary page displaying safety incident data, statistics, and trends.

### Page Header

#### Title
- **Text**: "Overview"
- **Style**: Large, bold heading

#### Filter Controls (Top Right)

##### 1️⃣ Incident Type Dropdown

**UI Element**: Blue button-styled dropdown
- **Default Value**: "All Incidents"
- **Options**:
  - All Incidents
  - Fall Detected
  - PPE Violation
  - Intrusion

**API Integration**:
```
API Endpoint: GET /api/overview/events/
Query Parameters: 
  - type: <selected_type> (e.g., "FALL_DETECTED", "PPE_VIOLATION", "INTRUSION")
  - date: <selected_date>
```

**When Changed**:
1. Updates `selectedIncidentType` state
2. Resets pagination to page 1
3. Triggers API call to fetch filtered events
4. Updates incident cards display

---

##### 2️⃣ Date Picker Calendar

**UI Element**: Blue button-styled date input with calendar icon
- **Default Value**: Today's date (YYYY-MM-DD format)
- **Input Type**: HTML5 date picker

**API Integration**:
```
API Endpoint: GET /api/overview/events/
Query Parameters: 
  - date: <selected_date> (YYYY-MM-DD format)
  - type: <selected_type>
```

**When Changed**:
1. Updates `selectedDate` state
2. Resets pagination to page 1
3. Triggers API call to fetch events for that date
4. Updates all incident cards

---

### Incident Cards Grid

**Layout**: Responsive grid (1-3 columns based on screen size)
- Mobile: 1 column
- Tablet: 2 columns
- Desktop: 3 columns

**Pagination**: 6 items per page

#### Individual Incident Card

Each card is a white container with shadow that displays:

**Left Section** (Text Information):
- **Incident ID**: Format `EVT-{event_id}` (blue text)
- **Time**: Event timestamp in local time format
- **Location**: Camera location (e.g., "Warehouse A")
- **Type**: Human-readable event type
  - "Fall Detected" for `FALL_DETECTED`
  - "PPE Violation" for `PPE_VIOLATION`
  - "Intrusion" for `INTRUSION`
  - "No Helmet" for `NO_HELMET`
  - "No Vest" for `NO_VEST`
  - "No Gloves" for `NO_GLOVES`

**Right Section** (Image Thumbnail):
- **Width**: 128px
- **Source**: `image_url` from API
- **Fallback**: ⚠️ emoji if image fails to load or is not available

**API Integration**:
```
API Endpoint: GET /api/overview/events/
Response Format:
[
  {
    "event_id": 123,
    "event_type": "FALL_DETECTED",
    "timestamp": "2024-05-14T10:30:00Z",
    "location": "Warehouse A",
    "image_url": "http://localhost:8000/media/frames/frame_123.jpg"
  },
  ...
]
```

**Empty State**:
- Displays when no incidents match the filters
- Message: "No incidents found for the selected date and type."

---

### Pagination Controls

**UI Elements**: 
- **Previous Button**: Left chevron icon
- **Page Numbers**: Clickable buttons (1, 2, 3, ...)
- **Next Button**: Right chevron icon

**Behavior**:
- Current page highlighted in blue
- Disabled buttons shown with reduced opacity
- Calculates total pages: `Math.ceil(incidents.length / 6)`

**No API Interaction**: Pagination is client-side based on fetched data

---

### Summary Section

A horizontal divider separates the incident cards from the charts section.

#### Section Header

**Title**: "Summary"

**Filter Controls** (Top Right):

##### 3️⃣ Time Range Dropdown

**UI Element**: Standard bordered dropdown
- **Default Value**: "Today"
- **Options**:
  - Today (last 24 hours)
  - This Week (last 7 days)
  - This Month (last 30 days)

**API Integration**:
```
API Endpoint: GET /api/overview/graph/
Query Parameters:
  - time_range: "today" | "week" | "month"
  - type: <selected_type>
```

**When Changed**:
1. Updates `chartTimeRange` state
2. Sets loading state
3. Fetches new graph data
4. Updates both line and bar charts

---

##### 4️⃣ Chart Incident Type Dropdown

**UI Element**: Standard bordered dropdown
- **Default Value**: "All Types"
- **Options**:
  - All Types
  - Fall
  - PPE Violation
  - Intrusion

**API Integration**:
```
API Endpoint: GET /api/overview/graph/
Query Parameters:
  - time_range: <selected_range>
  - type: <selected_type> (optional, omitted if "all")
```

**When Changed**:
1. Updates `chartIncidentType` state
2. Triggers API call for filtered graph data
3. Updates all three charts

---

### Charts Grid

**Layout**: Responsive grid with 3 chart sections

---

#### Chart 1: Incidents Trend (Line Chart)

**Position**: Top left (spans 2 columns on desktop)
**Chart Type**: Line chart with dots
**Library**: Recharts

**Features**:
- **X-Axis**: Time labels (format depends on time range)
  - Today: "HH:MM" (e.g., "10:00", "14:00")
  - Week: Day abbreviation (e.g., "Mon", "Tue")
  - Month: "MMM DD" (e.g., "Jan 01", "Jan 15")
- **Y-Axis**: Count of incidents
- **Line Color**: Blue (#3B82F6)
- **Grid**: Dashed lines
- **Tooltip**: Shows value on hover

**API Integration**:
```
API Endpoint: GET /api/overview/graph/
Response Format:
[
  {
    "label": "10:00",
    "count": 5
  },
  {
    "label": "11:00",
    "count": 3
  },
  ...
]
```

**Loading State**: Shows "Loading..." in center
**Empty State**: Shows "No data available" when no incidents found

**Data Processing** (Backend):
- For "Today": Aggregates by hour (24 data points)
- For "Week": Aggregates by day (7 data points)
- For "Month": Aggregates by day (30 data points)
- Fills missing time periods with zero values

---

#### Chart 2: Incident Overview (Donut Chart)

**Position**: Top right (1 column)
**Chart Type**: Donut/Pie chart with legend
**Library**: Recharts

**Features**:
- **Inner Radius**: 50px
- **Outer Radius**: 80px
- **Colors**:
  - Fall: Blue (#60A5FA)
  - PPE: Green (#34D399)
  - Intrusion: Red (#F87171)
- **Legend Below Chart**:
  - Total Events count
  - Each type with color indicator and percentage

**API Integration**:
```
API Endpoint: GET /api/overview/summary/
Query Parameters:
  - date: <selected_date>
  - type: <selected_type>
  
Response Format:
{
  "total_events": 150,
  "type_count": 45,
  "percentage": 30.0
}
```

**Note**: The current implementation shows percentages derived from the summary data. The donut displays distribution of different incident types.

**Empty State**: Shows "No data available" when no summary data exists

---

#### Chart 3: Incidents Over Time (Bar Chart)

**Position**: Bottom (spans all 3 columns)
**Chart Type**: Bar chart with rounded corners
**Library**: Recharts

**Features**:
- **X-Axis**: Same labels as line chart (time-based)
- **Y-Axis**: Count of incidents
- **Bar Color**: Light blue (#60A5FA)
- **Rounded Corners**: Top corners rounded (8px radius)
- **Grid**: Dashed lines
- **Tooltip**: Shows count on hover

**API Integration**:
```
API Endpoint: GET /api/overview/graph/
```

**Uses same data as Line Chart** (Chart 1)

**Loading State**: Shows "Loading..." in center
**Empty State**: Shows "No data available"

---

## 3. Footer Section

**Position**: Bottom of Overview page

**Content**:
- ProDiSyn logo with gradient
- Company name: "ProDiSyn Innovations"
- Tagline: "Intelligence Embedded • Solutions Engineered"

**No API Interaction**

---

## API Summary

### Base URL
```
http://localhost:8000/api
```

### Available Endpoints

#### 1️⃣ Get Events (Incident Cards)
```
GET /api/overview/events/

Query Parameters:
  - date (optional): YYYY-MM-DD format
  - type (optional): FALL_DETECTED | PPE_VIOLATION | INTRUSION

Response: Array of events
[
  {
    "event_id": number,
    "event_type": string,
    "timestamp": ISO datetime string,
    "location": string,
    "image_url": string | null
  }
]
```

**Triggered By**:
- Date picker change
- Incident type dropdown change
- Page load

---

#### 2️⃣ Get Summary Statistics (Donut Chart)
```
GET /api/overview/summary/

Query Parameters:
  - date (optional): YYYY-MM-DD format
  - type (optional): Event type filter

Response: 
{
  "total_events": number,
  "type_count": number,
  "percentage": number (0-100)
}
```

**Triggered By**:
- Date picker change
- Incident type dropdown change
- Page load

---

#### 3️⃣ Get Graph Data (Line & Bar Charts)
```
GET /api/overview/graph/

Query Parameters:
  - time_range (optional): today | week | month (default: today)
  - type (optional): Event type filter

Response: Array of data points
[
  {
    "label": string (time label),
    "count": number
  }
]
```

**Triggered By**:
- Time range dropdown change
- Chart incident type dropdown change
- Page load

---

#### 4️⃣ Get All Events (General)
```
GET /api/events/

Response: All events with detailed information
```

**Not currently used in Overview page**

---

#### 5️⃣ Get Cameras
```
GET /api/cameras/

Response: All camera locations
```

**Not currently used in Overview page**

---

#### 6️⃣ Get Access Decisions
```
GET /api/decisions/

Response: Access decision records
```

**Not currently used in Overview page**

---

## 🔄 UI Events → API → Database Mapping

This section details exactly what happens at the database level for each UI interaction.

### Visual Flow Diagram

![UI to Database Flow](/home/rajanikanth/.gemini/antigravity/brain/48f0fa5b-d958-438f-8e6e-a705de5f0fd7/ui_event_api_database_flow_1770717621171.png)

This diagram shows the complete data flow from UI interactions through API calls to database queries.

---

### Quick Reference Table

| UI Event | API Endpoint | Query Params | Database Tables | What Gets Updated |
|----------|-------------|--------------|-----------------|-------------------|
| 📅 **Date Picker Change** | `/api/overview/events/`<br>`/api/overview/summary/` | `date=YYYY-MM-DD`<br>`type=<event_type>` | `events`, `cameras`, `frames`, `event_media_map` | Incident cards + Donut chart |
| 📋 **Incident Type Dropdown** | `/api/overview/events/`<br>`/api/overview/summary/` | `date=YYYY-MM-DD`<br>`type=<selected_type>` | `events`, `cameras`, `frames` | Incident cards + Donut chart |
| ⏱️ **Time Range = Today** | `/api/overview/graph/` | `time_range=today`<br>`type=<event_type>` | `events` (hourly aggregation) | Line chart + Bar chart (24 hours) |
| 📊 **Time Range = Week** | `/api/overview/graph/` | `time_range=week`<br>`type=<event_type>` | `events` (daily aggregation) | Line chart + Bar chart (7 days) |
| 📈 **Time Range = Month** | `/api/overview/graph/` | `time_range=month`<br>`type=<event_type>` | `events` (daily aggregation) | Line chart + Bar chart (30 days) |
| 🎯 **Chart Type Filter** | `/api/overview/graph/` | `time_range=<range>`<br>`type=<chart_type>` | `events` (filtered by type) | Line chart + Bar chart |
| ⏭️ **Pagination Click** | ❌ None | N/A | N/A (client-side) | Incident cards display |
| 🚪 **Logout Click** | ❌ None | N/A | N/A | Redirect to login |

---

### Event 1: Date Picker Change

**UI Action**: User selects a new date from the date picker calendar

**State Update**:
```javascript
setSelectedDate('2024-05-14')  // YYYY-MM-DD format
setCurrentPage(1)  // Reset to first page
```

**API Calls Triggered** (2 simultaneous calls):

#### Call 1: Fetch Events
```
GET http://localhost:8000/api/overview/events/?date=2024-05-14&type=FALL_DETECTED

Query Parameters:
  - date: "2024-05-14" (YYYY-MM-DD format)
  - type: "FALL_DETECTED" (or current selected type, omitted if "all")
```

**Backend Processing** (`api/views.py` - Line 47-53):
```python
# Parse the date string
search_date = datetime.strptime('2024-05-14', '%Y-%m-%d').date()

# Filter queryset
queryset = Event.objects.all().order_by('-timestamp')
queryset = queryset.filter(timestamp__date=search_date)
if event_type:
    queryset = queryset.filter(event_type__iexact=event_type)
```

**Database Query**:
```sql
SELECT e.event_id, e.event_type, e.timestamp, 
       c.location,
       f.storage_path as image_path
FROM events e
LEFT JOIN cameras c ON e.camera_id = c.camera_id
LEFT JOIN event_media_map emm ON e.event_id = emm.event_id AND emm.media_type = 'FRAME'
LEFT JOIN frames f ON emm.media_id = f.frame_id
WHERE DATE(e.timestamp) = '2024-05-14'
  AND e.event_type = 'FALL_DETECTED'
ORDER BY e.timestamp DESC;
```

**Response Format**:
```json
[
  {
    "event_id": 123,
    "event_type": "FALL_DETECTED",
    "timestamp": "2024-05-14T10:30:00Z",
    "location": "Warehouse A",
    "image_url": "http://localhost:8000/media/frames/frame_123.jpg"
  },
  {
    "event_id": 124,
    "event_type": "FALL_DETECTED",
    "timestamp": "2024-05-14T14:20:00Z",
    "location": "Construction Site B",
    "image_url": "http://localhost:8000/media/frames/frame_124.jpg"
  }
]
```

**UI Update**: Incident cards grid refreshes with events from the selected date

---

#### Call 2: Fetch Summary
```
GET http://localhost:8000/api/overview/summary/?date=2024-05-14&type=FALL_DETECTED

Query Parameters:
  - date: "2024-05-14"
  - type: "FALL_DETECTED" (optional)
```

**Backend Processing** (`api/views.py` - Line 72-91):
```python
# Filter by date
queryset = Event.objects.all()
queryset = queryset.filter(timestamp__date=search_date)

# Count total events
total_events = queryset.count()

# Count specific type
type_count = queryset.filter(event_type__iexact=event_type).count()

# Calculate percentage
percentage = (type_count / total_events) * 100 if total_events > 0 else 0
```

**Database Query**:
```sql
-- Total events count
SELECT COUNT(*) FROM events
WHERE DATE(timestamp) = '2024-05-14';

-- Type-specific count
SELECT COUNT(*) FROM events
WHERE DATE(timestamp) = '2024-05-14'
  AND event_type = 'FALL_DETECTED';
```

**Response**:
```json
{
  "total_events": 150,
  "type_count": 45,
  "percentage": 30.0
}
```

**UI Update**: Donut chart percentages update

---

### Event 2: Incident Type Dropdown Change

**UI Action**: User selects "PPE Violation" from the Incident Type dropdown

**State Update**:
```javascript
setSelectedIncidentType('PPE_VIOLATION')
setCurrentPage(1)
```

**API Calls Triggered** (2 calls):

#### Call 1: Fetch Filtered Events
```
GET http://localhost:8000/api/overview/events/?date=2024-05-14&type=PPE_VIOLATION
```

**Database Query**:
```sql
SELECT e.event_id, e.event_type, e.timestamp, c.location, f.storage_path
FROM events e
LEFT JOIN cameras c ON e.camera_id = c.camera_id
LEFT JOIN event_media_map emm ON e.event_id = emm.event_id
LEFT JOIN frames f ON emm.media_id = f.frame_id
WHERE DATE(e.timestamp) = '2024-05-14'
  AND LOWER(e.event_type) = 'ppe_violation'
ORDER BY e.timestamp DESC;
```

**UI Update**: Shows only PPE Violation incidents in the cards

---

#### Call 2: Fetch Updated Summary
```
GET http://localhost:8000/api/overview/summary/?date=2024-05-14&type=PPE_VIOLATION
```

**Database Query**:
```sql
SELECT COUNT(*) as total FROM events WHERE DATE(timestamp) = '2024-05-14';
SELECT COUNT(*) as type_count FROM events 
WHERE DATE(timestamp) = '2024-05-14' AND event_type = 'PPE_VIOLATION';
```

**UI Update**: Donut chart shows percentage of PPE violations

---

### Event 3: Time Range Dropdown Change (Chart Filter)

**UI Action**: User selects "This Week" from Time Range dropdown

**State Update**:
```javascript
setChartTimeRange('week')
```

**API Call**:
```
GET http://localhost:8000/api/overview/graph/?time_range=week&type=FALL_DETECTED
```

**Backend Processing** (`api/views.py` - Line 127-142):
```python
# Calculate start time (7 days ago)
now = timezone.now()
start_time = now - timedelta(days=6)

# Filter events
queryset = Event.objects.filter(timestamp__gte=start_time)
if event_type:
    queryset = queryset.filter(event_type__iexact=event_type)

# Aggregate by day
stats = queryset.annotate(
    day=TruncDay('timestamp')
).values('day').annotate(
    count=Count('event_id')
).order_by('day')
```

**Database Query**:
```sql
SELECT 
  DATE_TRUNC('day', timestamp) as day,
  COUNT(event_id) as count
FROM events
WHERE timestamp >= NOW() - INTERVAL '6 days'
  AND event_type = 'FALL_DETECTED'
GROUP BY DATE_TRUNC('day', timestamp)
ORDER BY day;
```

**Backend Data Processing**:
```python
# Fill in missing days with zero
days = {(now - timedelta(days=i)).date(): 0 for i in range(7)}
for item in stats:
    if item['day']:
        days[item['day'].date()] = item['count']

# Format response
data_points = []
for date_val, count in sorted(days.items()):
    data_points.append({
        'label': date_val.strftime('%a'),  # Mon, Tue, Wed...
        'count': count
    })
```

**Response**:
```json
[
  {"label": "Mon", "count": 5},
  {"label": "Tue", "count": 8},
  {"label": "Wed", "count": 3},
  {"label": "Thu", "count": 12},
  {"label": "Fri", "count": 7},
  {"label": "Sat", "count": 4},
  {"label": "Sun", "count": 9}
]
```

**UI Update**: Both Line Chart and Bar Chart update with 7 data points (one per day)

---

### Event 4: Time Range = "Today"

**API Call**:
```
GET http://localhost:8000/api/overview/graph/?time_range=today&type=all
```

**Backend Processing** (`api/views.py` - Line 110-125):
```python
# Get start of today
start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

# Aggregate by hour
stats = queryset.annotate(
    hour=TruncHour('timestamp')
).values('hour').annotate(
    count=Count('event_id')
).order_by('hour')

# Fill all 24 hours with data
hours = {start_time + timedelta(hours=i): 0 for i in range(24)}
```

**Database Query**:
```sql
SELECT 
  DATE_TRUNC('hour', timestamp) as hour,
  COUNT(event_id) as count
FROM events
WHERE timestamp >= CURRENT_DATE
GROUP BY DATE_TRUNC('hour', timestamp)
ORDER BY hour;
```

**Response** (24 data points):
```json
[
  {"label": "00:00", "count": 0},
  {"label": "01:00", "count": 0},
  {"label": "02:00", "count": 1},
  ...
  {"label": "10:00", "count": 5},
  {"label": "11:00", "count": 8},
  ...
  {"label": "23:00", "count": 2}
]
```

**UI Update**: Charts show hourly breakdown for the current day

---

### Event 5: Time Range = "This Month"

**API Call**:
```
GET http://localhost:8000/api/overview/graph/?time_range=month
```

**Backend Processing** (`api/views.py` - Line 144-158):
```python
# Calculate start time (30 days ago)
start_time = now - timedelta(days=29)

# Aggregate by day
stats = queryset.annotate(
    day=TruncDay('timestamp')
).values('day').annotate(
    count=Count('event_id')
).order_by('day')

# Fill 30 days
days = {(now - timedelta(days=i)).date(): 0 for i in range(30)}
```

**Database Query**:
```sql
SELECT 
  DATE_TRUNC('day', timestamp) as day,
  COUNT(event_id) as count
FROM events
WHERE timestamp >= NOW() - INTERVAL '29 days'
GROUP BY DATE_TRUNC('day', timestamp)
ORDER BY day;
```

**Response** (30 data points):
```json
[
  {"label": "Jan 15", "count": 3},
  {"label": "Jan 16", "count": 7},
  {"label": "Jan 17", "count": 5},
  ...
  {"label": "Feb 13", "count": 9}
]
```

**UI Update**: Charts show 30 days of data

---

### Event 6: Chart Incident Type Dropdown Change

**UI Action**: User selects "Intrusion" from Chart Type dropdown

**State Update**:
```javascript
setChartIncidentType('INTRUSION')
```

**API Call**:
```
GET http://localhost:8000/api/overview/graph/?time_range=today&type=INTRUSION
```

**Database Query**:
```sql
SELECT 
  DATE_TRUNC('hour', timestamp) as hour,
  COUNT(event_id) as count
FROM events
WHERE timestamp >= CURRENT_DATE
  AND LOWER(event_type) = 'intrusion'
GROUP BY DATE_TRUNC('hour', timestamp)
ORDER BY hour;
```

**UI Update**: Line and Bar charts show only Intrusion incidents

---

### Event 7: Pagination Click

**UI Action**: User clicks page "2" button

**State Update**:
```javascript
setCurrentPage(2)
```

**API Call**: ❌ **NONE** - No API call is made

**Data Processing**: Client-side slicing
```javascript
const startIndex = (2 - 1) * 6  // = 6
const displayedIncidents = incidents.slice(6, 12)
```

**UI Update**: Shows incidents 7-12 from already loaded data

---

### Event 8: Logout Button Click

**UI Action**: User clicks logout icon in sidebar

**State Update**:
```javascript
navigate('/login')
```

**API Call**: ❌ **NONE** - Currently no API call (token-based auth could be added)

**UI Update**: Redirects to login page

---

## 📊 Database Tables Referenced

Based on the API interactions, these PostgreSQL tables are queried:

### 1️⃣ **events** table
```sql
Columns used:
  - event_id (Primary Key)
  - event_type (VARCHAR) - Values: FALL_DETECTED, PPE_VIOLATION, INTRUSION, etc.
  - timestamp (TIMESTAMP) - When the event occurred
  - camera_id (Foreign Key) - Links to cameras table
```

### 2️⃣ **cameras** table
```sql
Columns used:
  - camera_id (Primary Key)
  - location (VARCHAR) - Display name like "Warehouse A"
```

### 3️⃣ **event_media_map** table
```sql
Columns used:
  - event_id (Foreign Key) - Links to events
  - media_id (Foreign Key) - Links to frames
  - media_type (VARCHAR) - 'FRAME' or 'VIDEO'
```

### 4️⃣ **frames** table
```sql
Columns used:
  - frame_id (Primary Key)
  - storage_path (VARCHAR) - Path to image file
```

---

## 🔍 Query Performance Notes

### Indexed Columns (Recommended)
For optimal performance, these columns should be indexed:

```sql
-- Events table
CREATE INDEX idx_events_timestamp ON events(timestamp);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_timestamp_date ON events(DATE(timestamp));

-- Event Media Map
CREATE INDEX idx_emm_event_id ON event_media_map(event_id);
CREATE INDEX idx_emm_media_type ON event_media_map(media_type);
```

### Query Optimization
- **Date filtering**: Uses `DATE(timestamp)` which may require functional index
- **Time aggregation**: Uses `DATE_TRUNC` for hourly/daily grouping
- **Count operations**: Aggregation functions used for statistics
- **Joins**: LEFT JOINs used to get camera location and frame images

---

## Component Interaction Flow

### On Page Load:
1. 🔄 Fetch events for today (all types)
2. 🔄 Fetch summary for today
3. 🔄 Fetch graph data for today

### When User Changes Date:
1. ✅ Update selectedDate state
2. ✅ Reset pagination to page 1
3. 🔄 Fetch events for new date
4. 🔄 Fetch summary for new date
5. ✅ Re-render incident cards

### When User Changes Incident Type (Top Filter):
1. ✅ Update selectedIncidentType state
2. ✅ Reset pagination to page 1
3. 🔄 Fetch filtered events
4. 🔄 Fetch filtered summary
5. ✅ Re-render incident cards and donut chart

### When User Changes Time Range (Chart Filter):
1. ✅ Update chartTimeRange state
2. ✅ Set loading state
3. 🔄 Fetch graph data for new range
4. ✅ Update line and bar charts

### When User Changes Chart Incident Type:
1. ✅ Update chartIncidentType state
2. 🔄 Fetch filtered graph data
3. ✅ Update line and bar charts

### When User Clicks Pagination:
1. ✅ Update currentPage state
2. ✅ Re-render incident cards with new slice of data
3. ❌ No API call (data already loaded)

---

## UI Mockups

### Complete Dashboard View

![Worker Safety Dashboard - Full View](/home/rajanikanth/.gemini/antigravity/brain/48f0fa5b-d958-438f-8e6e-a705de5f0fd7/overview_dashboard_ui_1770713492462.png)

This mockup shows:
- Left sidebar with navigation
- User profile section with Rajanikanth
- Main content area with filters
- Incident cards grid
- Charts section with statistics

---

### UI with Dropdowns Expanded

![Dashboard with Open Dropdowns](/home/rajanikanth/.gemini/antigravity/brain/48f0fa5b-d958-438f-8e6e-a705de5f0fd7/ui_with_dropdowns_open_1770713730562.png)

This mockup shows:
- **Incident Type Dropdown** open with all options visible (All Incidents, Fall Detected, PPE Violation, Intrusion)
- **Date Picker** with calendar popup
- **Time Range Dropdown** expanded showing Today, This Week, This Month
- **Chart Type Dropdown** showing All Types, Fall, PPE Violation, Intrusion
- All interactive dropdowns in their active state

---

### Detailed Incident Cards View

![Incident Cards Grid](/home/rajanikanth/.gemini/antigravity/brain/48f0fa5b-d958-438f-8e6e-a705de5f0fd7/detailed_incident_cards_1770713748520.png)

This mockup shows:
- Grid layout of 6 incident cards
- Each card structure: Incident ID (blue), Time, Location, Type on left
- Warning icon/thumbnail on right side
- Pagination controls with numbered buttons and arrows
- Clean card design with shadows

---

### Charts and Statistics Section

![Safety Statistics Charts](/home/rajanikanth/.gemini/antigravity/brain/48f0fa5b-d958-438f-8e6e-a705de5f0fd7/charts_section_detailed_1770713780653.png)

This mockup shows:
- **Line Chart** (Incidents Trend): 24-hour time axis with blue line and dots
- **Donut Chart** (Incident Overview): Multi-colored segments with total count and percentages
- **Bar Chart** (Incidents Over Time): Weekly data with light blue bars
- Clear labels, legends, and grid lines
- Professional data visualization

---

### Sidebar Component Detail

![Sidebar Navigation](/home/rajanikanth/.gemini/antigravity/brain/48f0fa5b-d958-438f-8e6e-a705de5f0fd7/sidebar_component_detail_1770713840445.png)

This mockup shows:
- **ProDiSyn Logo** with gradient (blue to orange) and checkmark icon
- **User Profile Section**: Avatar with "R", name "Rajanikanth", role "Administrator", logout icon
- **Navigation Menu**: 4 menu items with icons
  - Overview (active - highlighted in blue)
  - Incidents
  - User Management
  - Settings
- **Footer**: Version information

---

### Detailed Field Placement Diagram

![UI Component Layout & Field Placement](/home/rajanikanth/.gemini/antigravity/brain/48f0fa5b-d958-438f-8e6e-a705de5f0fd7/ui_field_placement_1770713522836.png)

This diagram shows:
- Exact placement of all dropdowns and buttons
- Incident card structure with labeled fields
- Chart layouts with legends and axes
- Interactive element positioning

---

## Technology Stack

### Frontend
- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **Routing**: React Router
- **HTTP Client**: Axios
- **Charts**: Recharts
- **Icons**: Lucide React
- **Styling**: CSS (Tailwind-like utility classes)

### Backend
- **Framework**: Django REST Framework
- **Database**: PostgreSQL (unmanaged models)
- **Query Optimization**: Django ORM aggregation functions

---

## Color Scheme

### Primary Colors
- **Blue**: `#3B82F6` (Primary actions, charts)
- **Light Blue**: `#60A5FA` (Chart bars, backgrounds)

### Status Colors
- **Red**: `#F87171` (Intrusion, errors)
- **Green**: `#34D399` (PPE compliance)
- **Orange**: `#F59E0B` (Warnings)

### Neutral Colors
- **Gray 100**: `#F3F4F6` (Background)
- **Gray 500**: `#6B7280` (Secondary text)
- **Gray 800**: `#1F2937` (Primary text)
- **White**: `#FFFFFF` (Cards, sidebar)

---

## Best Practices & Notes

### Performance
- Client-side pagination reduces API load
- Loading states prevent UI jank
- Error handling with fallback UI

### User Experience
- Clear visual hierarchy
- Responsive design for all screen sizes
- Accessible color contrasts
- Intuitive navigation

### Data Visualization
- Multiple chart types for different insights
- Consistent color coding
- Clear labels and legends
- Empty states for no data scenarios

---

## Future Enhancements

Based on the navigation menu, the following pages are planned but not yet implemented:

1. **Incidents Page**: Detailed incident management
2. **User Management Page**: User roles and permissions
3. **Settings Page**: System configuration

---

**Document Version**: 1.0  
**Last Updated**: February 10, 2026  
**Author**: ProDiSyn Innovations
