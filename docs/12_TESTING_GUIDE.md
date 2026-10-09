# Testing Guide - Worker Safety API

## Quick Start for Testing

The system provides scripts to easily add and remove test data for development and testing purposes.

## 📊 Generate Test Data

To add dummy data for testing the dashboard:

```bash
python3 generate_test_data.py
```

**What this creates:**
- 50 events for today's date
- Events spread across the last 12 hours
- Mix of incident types:
  - Fall Detected
  - Intrusion
  - PPE Violations (Helmet missing, Vest missing)
- Test data is tagged with camera location `TEST_DATA` (ID: 999)

**Example Output:**
```
🚀 Worker Safety API - Test Data Generator
==================================================
✅ Created test camera (ID: 999, Location: TEST_DATA)

📊 Creating 50 test events...
  Created 10/50 events...
  Created 20/50 events...
  Created 30/50 events...
  Created 40/50 events...
  Created 50/50 events...
✅ Successfully created 50 test events!

==================================================
📈 TEST DATA SUMMARY
==================================================
Total Events: 50
  - Fall Detected: 13
  - Intrusion: 12
  - PPE Violations: 25
==================================================
```

---

## 🧹 Remove Test Data

To clean up all test data and return to original state:

```bash
python3 cleanup_test_data.py
```

**What this removes:**
- All events created by the test camera (Location: TEST_DATA)
- Associated event detections
- The test camera itself

**Safety Features:**
- Asks for confirmation before deleting
- Only deletes data tagged as TEST_DATA
- Never touches your real/production data

**Example Output:**
```
🧹 Worker Safety API - Test Data Cleanup
==================================================

📊 Found 50 test events

⚠️  Are you sure you want to delete 50 test events? (yes/no): yes
✅ Deleted 30 event detections
✅ Deleted 50 test events
✅ Removed test camera (ID: 999, Location: TEST_DATA)

==================================================
✨ Cleanup complete! Your database is back to original state.
==================================================
```

---

## 🔄 Typical Testing Workflow

### 1. Start Fresh
```bash
# Clean up any existing test data
python3 cleanup_test_data.py

# Generate fresh test data
python3 generate_test_data.py
```

### 2. Test the UI
```bash
# Start backend (if not running)
python3 manage.py runserver 0.0.0.0:8000

# Start frontend (if not running)
cd worker-safety-ui
npm run dev
```

### 3. Access Dashboard
- Open browser: http://localhost:5173
- Login with: `admin` / `admin`
- Navigate to Overview page
- Test all filters and charts with the dummy data

### 4. Clean Up After Testing
```bash
# Remove test data
python3 cleanup_test_data.py
```

---

## 🎯 What to Test

### Incident Cards
- ✅ Verify cards display for today's date
- ✅ Filter by incident type (Fall, Intrusion, PPE)
- ✅ Check pagination (should have multiple pages)
- ✅ Verify missing items show for PPE violations

### Summary Charts
- ✅ Donut chart shows breakdown with colors
- ✅ Individual counts for Fall, Intrusion, Helmet, Vest
- ✅ Percentages calculate correctly

### Time-Based Charts
- ✅ Bar chart shows stacked colors for different types
- ✅ Data points distributed across hours
- ✅ Chart legend displays correctly
- ✅ Filtering by type updates the chart

### Filters
- ✅ Date picker filters events correctly
- ✅ Incident type dropdown works
- ✅ Chart time range selector (Today/Week/Month)
- ✅ Specific PPE type filters (Helmet/Vest)

---

## 🔍 Verifying Data

### Check Database Directly
```bash
# Connect to PostgreSQL
psql -U safelens_user -d worker_safety_db

# View test events
SELECT event_id, event_type, timestamp 
FROM events e 
JOIN camera c ON e.camera_id = c.camera_id 
WHERE c.location = 'TEST_DATA' 
ORDER BY timestamp DESC 
LIMIT 10;

# Count test events by type
SELECT event_type, COUNT(*) 
FROM events e 
JOIN camera c ON e.camera_id = c.camera_id 
WHERE c.location = 'TEST_DATA' 
GROUP BY event_type;
```

### Check API Responses
```bash
# Get all events
curl "http://localhost:8000/api/overview/events/" | jq

# Get summary
curl "http://localhost:8000/api/overview/summary/" | jq

# Get graph data
curl "http://localhost:8000/api/overview/graph/?time_range=today" | jq
```

---

## ⚙️ Customizing Test Data

You can modify `generate_test_data.py` to customize:

### Change Number of Events
```python
# Line 101 in generate_test_data.py
create_test_events(camera, count=100)  # Create 100 events instead of 50
```

### Change Time Range
```python
# Line 53 in generate_test_data.py
hours_ago = random.randint(0, 24)  # Spread across 24 hours instead of 12
```

### Change Event Type Distribution
```python
# Line 44-48 in generate_test_data.py
event_types = [
    'FALL_DETECTED',
    'FALL_DETECTED',  # More falls
    'INTRUSION',
    'PPE_VIOLATION',
    'PPE_VIOLATION',
    'PPE_VIOLATION',  # Even more PPE violations
]
```

---

## 🚨 Important Notes

1. **Test Data Isolation**
   - All test data uses Camera ID 999 with location "TEST_DATA"
   - Your real data is never affected
   - Easy to identify and remove

2. **Database Transactions**
   - Scripts use Django ORM for safe database operations
   - Foreign key relationships are handled automatically
   - No risk of data corruption

3. **Production Warning**
   - These scripts are for **DEVELOPMENT/TESTING ONLY**
   - Never run on production database
   - Always backup before testing

4. **Multiple Runs**
   - Running `generate_test_data.py` multiple times adds more data
   - The script will warn you if test data already exists
   - `cleanup_test_data.py` removes ALL test data at once

---

## 📝 Troubleshooting

### "No module named 'apps.api'"
```bash
# Make sure you're in the Worker-Safety-API directory
cd /home/rajanikanth/Worker-Safety-API
python3 generate_test_data.py
```

### "Test data already exists"
```bash
# Clean up first, then regenerate
python3 cleanup_test_data.py
python3 generate_test_data.py
```

### Events not showing in UI
1. Check date filter is set to today
2. Verify backend server is running
3. Check browser console for errors
4. Verify API response: `curl "http://localhost:8000/api/overview/events/"`

### Want to mix test and real data?
The test data uses a dedicated camera (ID: 999). Your real data from other cameras will still appear in the dashboard. Use the location filter or incident type filter to separate them.

---

## ✨ Best Practices

1. **Start Clean**: Always run cleanup before generating new test data
2. **Test Incrementally**: Generate data, test feature, clean up, repeat
3. **Document Issues**: Note any bugs or unexpected behavior while testing
4. **Use Version Control**: Commit working code before experimenting
5. **Regular Cleanup**: Don't let test data accumulate in your database

---

Happy Testing! 🎉
