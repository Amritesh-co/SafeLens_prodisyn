# AWS RDS First-Time Provisioning
=============================================================================

### 🛡️ Step 1: Find or Reset your Master Credentials
I (your AI assistant) cannot see your private passwords. You chose these when you created the RDS in the AWS Console.

1.  Log in to the **AWS Console** and go to **RDS**.
2.  Click **Databases** -> **safelensai-db**.
3.  Under **Connectivity & Security**, you will see the **Master Username** (usually `postgres` or `admin`).
4.  To reset the password:
    *   Click the **Modify** button (top right).
    *   Scroll to **Master Password** and type a new one (e.g., `SafeAdmin@123`).
    *   Scroll to the bottom, click **Continue**, and select **Apply Immediately**.

---

### 🚀 Step 2: Bootstrap the Database from EC2
Run these commands from your EC2 terminal once you have your Master Password.

**1. Login as the Master User:**
```bash
# Replace <MASTER_USER> with 'postgres' or 'admin'
psql -h safelensai-db.chmsomou27n1.ap-south-1.rds.amazonaws.com -U <MASTER_USER> -d postgres
```

**2. Create the SafeLens environment (type these into the psql prompt):**
```sql
-- Create the main database
CREATE DATABASE worker_safety_db;

-- Create the limited app user
CREATE USER safelens_user WITH PASSWORD 'SafeLens@123';

-- Give the app user power over its own database
GRANT ALL PRIVILEGES ON DATABASE worker_safety_db TO safelens_user;

-- Exit the prompt
\q
```

---

### 📦 Step 3: Initialize the System Schema
Now run the final schema script I created for you:

```bash
PGPASSWORD='SafeLens@123' psql -h safelensai-db.chmsomou27n1.ap-south-1.rds.amazonaws.com -U safelens_user -d worker_safety_db -f db/18_PRODUCTION_SCHEMA.sql
```

If you later need to apply a production schema patch or fix, use:

```bash
PGPASSWORD='SafeLens@123' psql -h safelensai-db.chmsomou27n1.ap-south-1.rds.amazonaws.com -U safelens_user -d worker_safety_db -f db/19_PRODUCTION_SCHEMA_FIX.sql
```

**Final Checklist**:
- [x] RDS Inbound Rule: PostgreSQL (5432) allowed for EC2 Security Group.
- [x] Master User: Password known/reset.
- [x] App User: `safelens_user` created.
- [x] Database: `worker_safety_db` created.
