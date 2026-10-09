# User Management & Authentication Guide

This guide explains how to manage users, how the UI authenticates with the API, and the role of permissions.

## 1. Creating Users

### Creating a Superuser (Admin)
The **Superuser** has full control over the system.
**Command:**
```bash
python3 manage.py createsuperuser
```
*Follow the prompts to set a Username, Email, and Password.*

### Creating Standard Users
You can create standard users via the **Django Admin Panel** (easiest way) or the shell.
1.  **Start Server**: `python3 manage.py runserver 0.0.0.0:8000`
2.  **Open Browser**: Go to `http://localhost:8000/admin/`
3.  **Login**: Use your Superuser credentials.
4.  **Add User**: Click **Users** -> **Add User**.
    *   Enter username/password.
    *   Save, then add details (First Name, Last Name, Email).
    *   **Permissions**: Mark as "Active".

## 2. Authentication Flow (UI -> API)

How does the Frontend (React) talk to the Backend (Django)?

1.  **Login Request**:
    *   User enters username/password in UI.
    *   UI sends `POST` request to `/api/login/`.
    *   **Payload**: `{"username": "admin", "password": "..."}`

2.  **Token Generation**:
    *   Django verifies credentials.
    *   If correct, it generates (or retrieves) an **Auth Token** from the `authtoken_token` table.
    *   **Response**: `{"token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"}`

3.  **Authenticated Requests**:
    *   The UI saves this token (e.g., in localStorage).
    *   For every subsequent request (e.g., fetching events), the UI adds a header:
        `Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b`
    *   Django checks this token to know **who** is asking.

## 3. Permissions & Groups

Why do we need them? To control **Access**.

### Permissions ("Can do X")
Permissions are specific rules.
*   *Example*: `api | event | Can delete event`
*   If a user has this permission, they can delete logs. If not, the API will reject the request with `403 Forbidden`.

### Groups ("Role-Based Access")
Instead of assigning 50 permissions to every new employee, you assign them to a **Group**.
*   **"Safety Officer" Group**:
    *   Has permissions: `View Events`, `View Cameras`, `Export Reports`.
*   **"System Admin" Group**:
    *   Has permissions: `Add User`, `Delete User`, `Configure Cameras`.

**Workflow**:
1.  Create a Group "Safety Viewers".
2.  Add specific permissions to it.
3.  Add "John Doe" to "Safety Viewers".
*John now automatically inherits all those permissions.*

## 4. Database Storage
All this data lives in your **Remote PostgreSQL Database** (public schema):
*   **Users**: `auth_user`
*   **Groups**: `auth_group`
*   **Tokens**: `authtoken_token`

## 5. Frequently Asked Questions

### Will this data be stored permanently?
**YES.**
All user data is stored in the **Remote PostgreSQL Database** (`192.168.1.42`). It is:
*   **Persistent**: It survives server restarts and crashes.
*   **Centralized**: Accessing the API from any machine will use the same user list.

### How do I check users via Command Line?
You can query the database directly to see who is registered.

**Option 1: Using Python (Easier)**
```bash
python3 manage.py shell -c "from django.contrib.auth.models import User; print([(u.username, u.email, u.is_superuser) for u in User.objects.all()])"
```

**Option 2: Using SQL (Advanced)**
```bash
PGPASSWORD='<DB_PASSWORD>' psql -h 192.168.1.42 -U safelens_user -d worker_safety_db -c "SELECT username, email, is_superuser, is_active FROM auth_user;"
```

### How do I create users via Command Line?
**To create a Superuser (Admin):**
```bash
python3 manage.py createsuperuser
```

**To create a Standard User (Script):**
You can run this python command in your terminal:
```bash
python3 manage.py shell -c "from django.contrib.auth.models import User; User.objects.create_user('john', 'john@example.com', 'password123')"
```
*(Replace 'john' and 'password123' with your desired credentials)*

### Who manages these users?
**The Superuser (Admin).**
*   The **Superuser** (created above) has the authority to log into the [Admin Panel](http://localhost:8000/admin/) and create, delete, or modify other users.
*   Standard users usually **cannot** manage other users.

### Can I manage users with direct SQL (without Python)?
**Checking Users:** YES.
You can list users using the `psql` tool with your database credentials:
```bash
# Login to Database Shell
PGPASSWORD='<DB_PASSWORD>' psql -h 192.168.1.42 -U safelens_user -d worker_safety_db

# Run Query
SELECT id, username, email, is_active FROM auth_user;
```

**Creating Users:** NO (Not Recommended).
Django **encrypts** passwords. If you try to `INSERT` a user with a plain text password like THIS:
```sql
-- DO NOT DO THIS! The user will NOT be able to log in.
INSERT INTO auth_user (username, password) VALUES ('test', 'password123');
```
...the login will fail because Django expects a hash (e.g., `pbkdf2_sha256$260000$....`).
**Always use `createsuperuser` or the Admin Interface to ensure passwords are encrypted correctly.**

## 6. Two Ways to Create Users (As Requested)

### Method 1: UI Based (Recommended)
This is the easiest and safest way.

1.  **Go to**: [http://localhost:8000/admin/](http://localhost:8000/admin/)
2.  **Login**: Use your superuser credentials (admin/admin).
3.  **Click**: "Users" -> "Add User" (Top right button).
4.  **Enter**: Username and Password.
5.  **Click**: "Save".

### Method 2: Direct DB / PSQL (Hard/Advanced)
If you **must** use `psql` to create a user, you cannot just type the password. You must generate a **Hash** first.

**Step A: Generate the Password Hash**
Run this one-line command in your terminal to get the hash for password `mypassword`:
```bash
python3 -c "from django.contrib.auth.hashers import make_password; print(make_password('mypassword'))"
```
*Output Example:* `pbkdf2_sha256$260000$....` (Copy this long string)

**Step B: Run the SQL Insert**
Now use that hash in your `psql` command:
```sql
INSERT INTO auth_user (password, last_login, is_superuser, username, first_name, last_name, email, is_staff, is_active, date_joined)
VALUES (
    'pbkdf2_sha256$YOUR_COPIED_HASH_STRING_HERE', 
    NULL, 
    FALSE, 
    'newuser', 
    '', 
    '', 
    'newuser@example.com', 
    FALSE, 
    TRUE, 
    NOW()
);
```

## 7. Security & Access Control (Important)

You asked: *"Does every system in this network have the right to change credentials?"*

The answer depends on **which password** they have.

### Scenario A: They have the Application Login (admin/admin)
*   **YES**, they can change credentials.
*   Anyone who can log in to `http://localhost:8000/admin/` as a Superuser can change passwords for everyone else.
*   **Fix:** Keep your Superuser password strong and secret.

### Scenario B: They have the Database Password (<DB_PASSWORD>)
*   **YES**, they can change credentials (via SQL).
*   Since your database is on the network (`192.168.1.42`), anyone who knows the database password (`<DB_PASSWORD>`) can connect using `psql` and overwrite passwords manually.
*   **Fix:**
    1.  Restrict who knows `<DB_PASSWORD>`.
    2.  Use a firewall to allow connections *only* from the API server IP, blocking other computers on the network.

### Summary
*   **Dashboard Users:** Can only view data (Read-Only).
*   **Admins:** Can change users and passwords.
*   **Network Intruders (with DB password):** Can change back-end data directly.

### Why does `http://localhost:8000/admin/` not work on other computers?
**"localhost" mean "THIS computer".**
If you type that into another computer, it looks for a web server on *that* computer, not yours.

**To access it from other computers in the network:**
Use your computer's IP address: **`192.168.1.38`**.

**Correct URL for others:**
[http://192.168.1.38:8000/admin/](http://192.168.1.38:8000/admin/)

### If they use THEIR IP address, will it work?
**NO.**
Think of your computer as a "TV Station".
*   **192.168.1.38** is the channel number of YOUR station.
*   Everyone else is a "TV". If they try to watch their own channel (their IP), they will see static (nothing), because they are not broadcasting anything.
*   **Everyone must tune into YOUR IP (`192.168.1.38`) to see your website.**

### Database IP vs Application IP (Crucial Difference)
You are absolutely correct. There are **TWO** different IP addresses involved here:

1.  **The Application (Django/Website)**
    *   **IP:** `192.168.1.38` (Port 8000)
    *   **User:** Your colleagues / Dashboard users.
    *   **Action:** They view the website. They cannot change the DB password.

2.  **The Database (PostgreSQL)**
    *   **IP:** `192.168.1.42` (Port 5432)
    *   **User:** Database Administrators / Intruders.
    *   **Action:** If they connect here with the password `<DB_PASSWORD>`, **YES**, they can change *everything* (users, passwords, data).
    *   **Risk:** This is why protecting the DB password (`<DB_PASSWORD>`) is so important. Anyone with that password and connection to `.42` has full power.

### Common Mistakes
**1. Attempting to visit the Database in a Browser**
*   **bad:** `http://192.168.1.42:5432/admin/`
*   **Why it fails:** This is a **Database**, not a **Website**. Browsers (Chrome/Edge) speak "HTTP". Databases speak "PostgreSQL Protocol". They are different languages.
*   **Correction:** You must view the **Website IP** (`192.168.1.38:8000`), which *talks* to the database for you.

**2. Using "localhost" on other machines**
*   **Bad:** `http://localhost:8000` (on a colleague's laptop)
*   **Correction:** `http://192.168.1.38:8000`

### What is "Staff Status"?
In the image you saw, **Staff Status** determines **who can login to this Admin Panel**.

*   ✅ **Green Check (Active):** This user can log in to `/admin/` and manage data. (e.g., specific managers).
*   ❌ **Red X (Inactive):** This user is a **Regular User**. They can log in to the **Main Dashboard** to view safety data, but they strictly **cannot** enter the Admin Panel to change network settings or user accounts.

**Best Practice:**
Only give "Staff Status" to people who actually need to manage the system. Keep it turned **OFF** for regular viewers.

### How do I know who logged in?
By default, Django tracks the **Last Login** time, but not a full history of every login/logout.

**1. Check "Last Login" in Admin Panel:**
*   Go to `http://192.168.1.38:8000/admin/auth/user/`
*   Look at the **"Last login"** column for each user.

**2. Check Admin Actions (Changes):**
*   Go to `http://192.168.1.38:8000/admin/`
*   In the top right, look at **"Racent Actions"**. This shows who changed what (e.g., "admin added user rajanikanth").

**3. Check via Command Line:**
You can see the last login time for everyone:
```bash
PGPASSWORD='<DB_PASSWORD>' psql -h 192.168.1.42 -U safelens_user -d worker_safety_db -c "SELECT username, last_login FROM auth_user;"
```

### Understanding "Logged In" Status (Important)
You asked: *"I am not understanding logged in status and out and time"*

Here is the technical reality of how web servers work:

1.  **"Status" (Online vs Offline):**
    *   **Django DOES NOT know if a user is "Online" right now.**
    *   Websites are "stateless". The user asks for a page, the server sends it, and then forgets them until they ask again.
    *   There is no green light/red light for "Online" unless we build a complex custom system using WebSockets.

2.  **"Logged Out" Time:**
    *   **Django DOES NOT verify when a user logs out.**
    *   When a user clicks "Logout", their browser just deletes the Key/Token. The server doesn't necessarily record "User X left at 5:00 PM".

**Summary of what is possible:**
*   ✅ **We Know:** The exact second they **Started** using the system (`last_login`).
*   ❌ **We Do Not Know:** The exact second they **Stopped** or if they are currently looking at the screen.

**Note:** To get a full history log of every login (audit trail), we would need to install extra plugins (like `django-axes` or custom logging), which is not currently set up.

---

## 8. API Endpoints & Frontend Integration

The User Management system is built around Python's **Django REST Framework (DRF)**.

### A. The Backend Code (Django)
1. **The Database Model**: We use Django’s built‑in `User` model (`django.contrib.auth.models.User`). This handles secure password hashing, roles, and status automatically. We also use a custom `UserActivityLog` model to track sessions.
2. **The Serializers (`api/serializers.py`)**: 
   - `UserSerializer` exposes `['id', 'username', 'email', 'password', 'last_login', 'date_joined', 'is_staff', 'is_active']`.
   - `UserActivityLogSerializer` exposes the login/logout history.
3. **The ViewSets (`api/views.py`)**: 
   - `UserViewSet`: Handles GET, POST, PATCH, PUT, and DELETE for users.
   - `UserActivityLogViewSet`: Handles GET for session history.
   - **CRITICAL**: Both viewsets use `permission_classes = [IsAdminUser]` to ensure only Admins can access or modify this data.

### B. The Frontend Code (React & Axios)
1. **API Service (`worker-safety-ui/src/services/api.ts`)**:
   We define clean functions that use Axios to make HTTP requests to the backend endpoints.
   ```javascript
   export const usersAPI = {
       getAll: () => api.get('/users/'),                       // GET request
       create: (data: any) => api.post('/users/', data),       // POST request
       update: (id: number, data: any) => api.patch(`/users/${id}/`, data), // PATCH request
       delete: (id: number) => api.delete(`/users/${id}/`),    // DELETE request
   }
   ```
   *Note: The `api` Axios instance automatically intercepts these calls and injects the `Authorization: Token <your_token>` header, or redirects to `/login` if a 401 is returned.*

2. **UI Component (`worker-safety-ui/src/components/UserManagement.tsx`)**:
   When the page loads, `useEffect` triggers `fetchUsers()`. The backend responses are extracted from `data.results` (because Django auto-paginates the response).
   ```javascript
   const fetchUsers = async () => {
       const response = await usersAPI.getAll()
       // Django returns paginated JSON: { count: 3, results: [...] }
       // We extract the array of users here:
       setUsers(response.data.results || []) 
   }
   ```

---

## 9. How to Test & Verify via CLI (`curl`)

You can execute the exact same commands the React UI runs using your terminal. 

*First, get an Admin token from the `/api/login/` endpoint:*
```bash
TOKEN=$(curl -s -X POST -H "Content-Type: application/json" -d '{"username":"admin","password":"<ADMIN_PASSWORD>"}' http://127.0.0.1:8000/api/login/ | jq -r .token)
```

### A. Read / List Users (GET)
This returns the paginated JSON list of users.
```bash
curl -s -X GET http://127.0.0.1:8000/api/users/ \
  -H "Authorization: Token $TOKEN" | jq .
```

### B. Read Session History (GET)
This returns the login/logout logs.
```bash
curl -s -X GET http://127.0.0.1:8000/api/activity-logs/ \
  -H "Authorization: Token $TOKEN" | jq .
```

### C. Create a New User (POST)
Creates a new standard user account.
```bash
curl -s -X POST http://127.0.0.1:8000/api/users/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username": "newworker", "password": "password123", "email": "worker@example.com"}' | jq .
```

### D. Update a User's Password (PATCH)
Use `PATCH` to update a specific field. Replace `[ID]` with the user's numeric ID (e.g., `3`). 
*(Note: Changing a password via the API automatically invalidates their active sessions!)*
```bash
curl -s -X PATCH http://127.0.0.1:8000/api/users/[ID]/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"password": "NewStrongPassword123!"}' | jq .
```

### E. Delete a User (DELETE)
Removes the user entirely. Replace `[ID]` with the user's numeric ID. A successful delete returns `HTTP 204 No Content` (so `curl` will output nothing).
```bash
curl -s -X DELETE http://127.0.0.1:8000/api/users/[ID]/ \
  -H "Authorization: Token $TOKEN"
```
