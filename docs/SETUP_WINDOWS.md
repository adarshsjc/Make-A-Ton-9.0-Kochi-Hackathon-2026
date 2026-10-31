# Setup on Windows 10/11

## 1. Install PostgreSQL

Download the official Windows installer from https://www.postgresql.org/download/windows/. Select PostgreSQL Server, pgAdmin 4 and Command Line Tools. Keep the default port `5432` and remember the password you set for the `postgres` administrator.

In pgAdmin's Query Tool (connected to the local server), create the application role and database:

```sql
CREATE ROLE brightloop_app WITH LOGIN PASSWORD 'your-local-password';
CREATE DATABASE brightloop OWNER brightloop_app;
```

Use a unique strong local password. Do not commit it. You can run the SQL in SQL Shell (psql) instead.

## 2. Install Python 3.12

Download Python 3.12.x from https://www.python.org/downloads/windows/. During installation enable **Add Python to PATH**. Verify in PowerShell:

```powershell
py -3.12 --version
```

## 3. Create the virtual environment and install packages

Open PowerShell in the extracted project folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation, use Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

Edit `.env` with the local PostgreSQL password. Generate/apply migrations as described in README.md, create a superuser, then run the server.
