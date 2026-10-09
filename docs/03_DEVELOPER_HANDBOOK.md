# Developer Handbook: Worker Safety API

This comprehensive guide explains the entire project lifecycle: from how it was created to how it works, what dependencies are used, and how to develop further.

## 1. Project Overview

The **Worker Safety API** is a backend service built using **Django** and **Django REST Framework (DRF)**.

### Purpose
To serve as a read-only interface (API layer) between the **Worker Safety Database** (PostgreSQL) and the **Frontend Dashboard**. It does not process video or detect safety events itself; it simply exposes the data that other systems have already written to the database.

---

## 2. Technology Stack & Dependencies

Here is what we installed and why:

| Package | Purpose |
| :--- | :--- |
| **`django`** | The high-level Python web framework used to build the application structure. |
| **`djangorestframework`** | A powerful toolkit for building Web APIs (serialization, viewsets). |
| **`psycopg2-binary`** | The PostgreSQL adapter for Python. Allows Django to talk to your `worker_safety_db`. |
| **`django-cors-headers`** | Middleware to handle Cross-Origin Resource Sharing (CORS). Essential for allowing your frontend (running on a different port) to fetch data from this API. |
| **`whitenoise`** | Simplifies static file serving for web apps. |
| **`gunicorn`** | A production-grade WSGI HTTP Server for running the app in deployment. |
| **`pytest`, `flake8`, `black`** | Tools for testing (`pytest`), checking code style (`flake8`), and auto-formatting (`black`) to keep code clean. |

---

## 3. How the Project Works (The Flow)

When a user (or the frontend) makes a request, here is the journey:

1.  **Request Entry**: A request hits the server (e.g., `GET /api/overview/events/`).
2.  **`safelensai/urls.py`**: The main URL configuration routes the request to the `api` app.
3.  **`api/urls.py`**: This file looks at the path and decides which **ViewSet** should handle it (e.g., `OverviewViewSet`).
4.  **`api/views.py`**: The ViewSet executes the logic.
    -   It queries the database using **Models** (`api/models.py`).
    -   It applies filters (like `date` or `type`).
5.  **`api/models.py`**: These define the structure of your database tables.
    -   **Crucial Note**: We use `managed = False`. This means Django **does not create tables**. It simply maps to the existing tables in `worker_safety_db`.
6.  **`api/serializers.py`**: The data from the database (Python objects) is converted into JSON format that the frontend can understand.
7.  **Response**: The JSON data is sent back to the user.

---

## 4. Project Structure

```
Worker-Safety-API/
├── manage.py                # Command-line utility for administrative tasks
├── requirements.txt         # List of all dependencies
├── safelensai/       # Main configuration folder
│   ├── settings.py          # Database config, installed apps, middleware
│   ├── urls.py              # Global URL routing
│   └── wsgi.py              # Entry point for WSGI servers (like Gunicorn)
└── api/                     # The main application app
    ├── models.py            # Database schema definitions (read-only)
    ├── serializers.py       # Converts DB models to JSON
    ├── views.py             # API logic (filtering, aggregation)
    └── urls.py              # API-specific URL routing
```

---

## 5. How to Run & Develop

### Starting Point
The entry point for development is `manage.py`.

1.  **Start the Server**:
    ```bash
    python3 manage.py runserver 0.0.0.0:8000
    ```
2.  **Access the API**:
    Open `http://localhost:8000/api/` in your browser. DRF provides a browsable web interface.

### How to Add a New Feature
If you want to add a new endpoint (e.g., "Worker Attendance"):

1.  **Model (`api/models.py`)**: Define the `WorkerAttendance` class matching your DB table.
2.  **Serializer (`api/serializers.py`)**: Create `WorkerAttendanceSerializer`.
3.  **View (`api/views.py`)**: Create `WorkerAttendanceViewSet`.
4.  **URL (`api/urls.py`)**: Register the router: `router.register('attendance', WorkerAttendanceViewSet)`.

### How to Verify
We included a script `check_api.py` to quickly test if endpoints work:
```bash
python3 check_api.py
```

---

## 6. Key Configuration Details
-   **Database**: Configured in `safelensai/settings.py`. It connects to `localhost` on port `5432` (PostgreSQL default).
-   **Static Files**: Handled by `whitenoise` so images/CSS work even in simple deployments.
-   **CORS**: Configured to allow all origins (`CORS_ALLOW_ALL_ORIGINS = True`) for easier development interfacing with frontends.
