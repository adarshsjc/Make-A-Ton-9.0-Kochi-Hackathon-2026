# Setup on Arch Linux

Commands are intended for a normal Arch install with sudo access.

## 1. Install PostgreSQL

```bash
sudo pacman -Syu postgresql
```

Initialize the default cluster only if it has not already been initialized:

```bash
if [ ! -s /var/lib/postgres/data/PG_VERSION ]; then
  sudo -iu postgres initdb -D /var/lib/postgres/data --locale=C.UTF-8 --encoding=UTF8
fi
```

Start and enable PostgreSQL:

```bash
sudo systemctl enable --now postgresql
systemctl status postgresql
```

## 2. Create a local project database

```bash
sudo -iu postgres psql
```

Run the following SQL. Use a different strong password on each machine; do not commit it:

```sql
CREATE ROLE brightloop_app WITH LOGIN PASSWORD 'your-local-password';
CREATE DATABASE brightloop OWNER brightloop_app;
\q
```

Verify:

```bash
psql -h 127.0.0.1 -U brightloop_app -d brightloop
```

## 3. Install Python 3.12 if necessary

Check first:

```bash
python3.12 --version
```

If unavailable, Arch users can install `uv` and use it to provide a managed Python 3.12 interpreter:

```bash
sudo pacman -S uv
uv python install 3.12
```

Then clone/open the project directory and create the environment. Use whichever path applies:

```bash
# If python3.12 is on PATH:
python3.12 -m venv .venv
# Otherwise, use uv's managed interpreter:
uv venv --python 3.12 .venv

source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with the PostgreSQL password. Generate/apply migrations as described in README.md, create a superuser, then run the server.
