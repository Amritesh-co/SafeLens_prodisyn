# Project Architecture & Code Walkthrough

This document explains **how the project was created**, **where it starts**, and provides a **line-by-line breakdown** of critical files, classes, and functions.

---

## 1. How the Project Was Created (The Setup Story)

This is a standard Django project structure created using the following commands:

1.  **Initialize Project**:
    ```bash
    django-admin startproject safelensai .
    ```
    *Creates the `manage.py` and the main `safelensai/` configuration folder.*

2.  **Create the API App**:
    ```bash
    python manage.py startapp api
    ```
    *Creates the `api/` folder where all our custom logic lives.*

3.  **Database Introspection**:
    Since we are connecting to an *existing* database, we didn't write `models.py` by hand. We used:
    ```bash
    python manage.py inspectdb > api/models.py
    ```
    *This automatically generated the Python classes matching your PostgreSQL tables.*

---

## 2. The Entry Point (How it Starts)

When you run `python manage.py runserver`, here is the chain of events:

1.  **`manage.py`**: The command-line utility. It points Django to `safelensai/settings.py`.
2.  **`safelensai/settings.py`**: Loads configuration (database credentials, installed apps like `'rest_framework'` and `'apps.api'`).
3.  **`safelensai/urls.py`**: The "Traffic Cop". It sees the path `/api/` and sends it to `apps.api.urls`.
4.  **`api/urls.py`**: The "Local Guide". It sees `/events/` and sends it to the `EventViewSet` in `views.py`.

---

## 3. Code Walkthrough (File by File)

### A. Configuration Files

#### `manage.py`
-   **Purpose**: The command-line interface for running the server, migrations, etc.
-   **Key Function**: `main()` - Sets the settings module and executes command-line arguments.

#### `safelensai/settings.py`
-   **Purpose**: Global configuration.
-   **Key Sections**:
    -   `INSTALLED_APPS`: Registers `'apps.api'`, `'rest_framework'`, `'corsheaders'`.
    -   `DATABASES`: Contains the PostgreSQL credentials (`safelens_user`, etc.).

#### `safelensai/urls.py`
-   **Purpose**: Top-level URL routing.
-   **Key Code**:
    ```python
    path('api/', include('apps.api.urls'))  # Routes everything starting with 'api/' to our app
    ```

---

### B. Application Files (`api/`)

#### 1. `api/models.py`
**Purpose**: Defines the structure of the database tables.
**Key Classes**:
-   `Event`: Maps to `events` table. Represents a safety incident.
-   `Camera`: Maps to `camera` table. info about cameras.
-   `EventMediaMap`: Links an `Event` to a `Frame` (image).
-   `Frame`: Stores the file path (`storage_path`) of the image.

*Note: All classes have current `Meta: managed = False`, meaning Django won't change the DB schema.*

#### 2. `api/serializers.py`
**Purpose**: Converts Python objects (Models) into JSON format for the API.
**Key Classes**:
-   `EventSerializer`:
    -   **Usage**: Used for the standard /events/ endpoint.
    -   **Nesting**: Includes `CameraSerializer` (to show camera location) inside the event data.
-   `OverviewEventSerializer`:
    -   **Usage**: Specifically for the "Overview" page.
    -   **Key Method**: `get_image_url(obj)` - This custom function manually queries `EventMediaMap` and `Frame` tables to find the image path for an event.

#### 3. `api/views.py`
**Purpose**: The "Brain" that handles requests. logic.
**Key Classes**:
-   `EventViewSet`: Standard CRUD (Create, Read, Update, Delete) view.
    -   `queryset = Event.objects.all()`: Fetches all events.
-   `OverviewViewSet`: Custom view for the dashboard needs.
    -   **Methods**:
        -   `events(self, request)`:
            -   **Usage**: Lists events but adds filtering logic.
            -   **Logic**: Checks if `?date=` or `?type=` is in the URL, filters the query, and uses `OverviewEventSerializer`.
        -   `summary(self, request)`:
            -   **Usage**: Calculates stats.
            -   **Logic**: Counts `total_events` vs specific type events to return a percentage.
        -   `graph(self, request)`:
            -   **Usage**: Prepares data for charts.
            -   **Logic**: Uses database aggregation (`TruncHour`, `TruncDay`) to group events by time buckets and counts them.

#### 4. `api/urls.py`
**Purpose**: Routes API-specific URLs to Views.
**Key Code**:
-   `router.register(...)`: Automatically creates URLs like `/events/`, `/events/1/`, etc.
-   We registered `overview` here so `/api/overview/events/` works.

---

## Summary of Data Flow
1.  **Frontend** asks for "Overview Events for Today".
2.  **`api/urls.py`** sends request to `OverviewViewSet.events`.
3.  **`OverviewViewSet.events`** (in `views.py`) filters `Event` rows by today's date.
4.  **`OverviewEventSerializer`** (in `serializers.py`) takes those events, looks up their camera location and image path.
5.  **Django** returns the JSON response.
