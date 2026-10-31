# Brightloop — Subscription Management System

Brightloop is a web-based subscription operations system for managing a recurring-revenue business. It brings customer accounts, product and plan catalogues, quotations, subscription lifecycle management, recurring billing, invoices, payments, discounts and finance reporting into one Django application.

The project is implemented as a **Django modular monolith** with **PostgreSQL** as the primary database. The browser interface uses Django templates with local HTML, CSS and JavaScript. Django REST Framework exposes the application API.

## Contents

- [Features](#features)
- [Technology stack](#technology-stack)
- [Application structure](#application-structure)
- [Requirements](#requirements)
- [Local setup](#local-setup)
- [Run and test](#run-and-test)
- [Demo data](#demo-data)
- [Main web pages](#main-web-pages)
- [API overview](#api-overview)
- [Typical end-to-end workflow](#typical-end-to-end-workflow)
- [Business rules and data integrity](#business-rules-and-data-integrity)
- [Current implementation boundaries](#current-implementation-boundaries)
- [Security and deployment notes](#security-and-deployment-notes)
- [Further documentation](#further-documentation)

## Features

### Accounts and access control

- Custom user model authenticated by email.
- Customer registration, login, logout and password-reset pages.
- Customer profile management for personal and billing details.
- Separate business roles: `ADMIN`, `STAFF` and `CUSTOMER`.
- Public registration always creates a customer account; customers cannot select an elevated role during registration.
- Customers can view their own subscription and invoice records. Server-side queryset filtering enforces ownership.
- Administrator-only staff-account creation and Django Admin access controls.

### Product catalogue and subscription plans

- Products with type, sale price, cost price, description and active status.
- Product variants with attributes, SKU and price adjustments.
- Tax rules.
- Subscription plans with recurring price, billing interval and interval count, minimum quantity, availability dates, optional tax and lifecycle permissions.
- Browser pages for product/variant creation and subscription-plan creation. Broader record administration is also available through the API and Django Admin, subject to permissions.

### Quotations and subscriptions

- Reusable quotation templates with product lines.
- Staff-created custom quotations using a customer, plan, product, optional variant, quantity and tax rule.
- Quotation validity dates and conversion to subscriptions.
- Subscription detail pages with lifecycle controls.
- Validated transitions for confirmation, activation, pause, resume, early close and renewal, subject to plan rules and the caller's role.
- Customers can view their own subscriptions and use the permitted lifecycle actions on their own records.

### Billing, invoices and payments

- Manually triggered recurring billing for subscriptions that are due.
- One invoice per subscription and billing period, protected by a database uniqueness constraint.
- Invoice confirmation and cancellation workflows for internal users.
- Invoice detail and browser print view with a **Print / Save PDF** action.
- Staff can record partial or full payments and track the remaining balance.
- Customers can view only their own invoices and invoice details.
- Invoice send action in the HTML workflow records a send event and makes a best-effort attempt to send an email through the configured Django email backend. Actual delivery depends on email configuration. The API send action records the send timestamp; it does not itself send an email.

### Discounts and finance

- Fixed-amount and percentage discount rules.
- Discount scopes, validity dates, minimum purchase and usage limits.
- Product-specific applicability where configured.
- Finance dashboard with revenue collected, outstanding balances, overdue amounts and invoice filtering.
- Dashboard and finance figures are calculated from application database records.

### API

- Django REST Framework API under `/api/v1/`.
- Session-based authentication and permission checks.
- Pagination, filtering, search and ordering where configured.
- Dedicated customer endpoints for the authenticated user's own invoices and subscriptions.

## Technology stack

| Component | Version / choice |
|---|---|
| Python | 3.12.x |
| Django | 5.2.18 |
| Django REST Framework | 3.18.1 |
| django-filter | 26.2 |
| PostgreSQL | 18.x used for team development |
| Psycopg | 3.x (`psycopg[binary]`, `>=3.2,<4`) |
| Environment configuration | `python-dotenv` |
| Frontend | Django templates, HTML, CSS and JavaScript |
| UI assets | Local CSS and JavaScript; no Node.js build step |

Install the dependencies from `requirements.txt`; it is the authoritative dependency list.

## Application structure

```text
brightloop/
├── accounts/        Custom user model, profiles, authentication and account APIs
├── catalog/         Products, product variants, taxes and subscription plans
├── subscriptions/  Quotation templates, quotations, subscriptions and lifecycle services
├── billing/         Discount rules, invoices, invoice lines, payments and billing services
├── dashboard/       Dashboard aggregates, views and demo-data command
├── common/           Shared permissions and document-number helpers
├── config/           Django settings, API index and root URL configuration
├── docs/             API examples, schema and platform setup notes
├── scripts/          Linux and Windows setup helpers
├── templates/        Account, dashboard, catalogue, subscription and billing pages
├── static/           Local CSS and JavaScript assets
├── manage.py
├── requirements.txt
└── .env.example
```

## Requirements

- Python 3.12
- PostgreSQL (the configured default database backend)
- Git

Platform-specific notes are available in [docs/SETUP_ARCH_LINUX.md](docs/SETUP_ARCH_LINUX.md) and [docs/SETUP_WINDOWS.md](docs/SETUP_WINDOWS.md).

## Local setup

The following setup uses PostgreSQL. Each developer should use a separate local database and private credentials.

### 1. Create the PostgreSQL role and database

Connect to PostgreSQL as an administrator and run the following SQL. Replace the example password with a unique local password:

```sql
CREATE ROLE brightloop_app WITH LOGIN PASSWORD 'replace-with-a-local-password';
CREATE DATABASE brightloop OWNER brightloop_app;
```

The default connection is `127.0.0.1:5432`. Do not expose the database server publicly for ordinary development.

### 2. Create and activate a Python virtual environment

**Linux / macOS shell:**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

On Arch Linux, if Python 3.12 is not installed, the `uv` Python manager can provide it:

```bash
uv python install 3.12
uv venv --python 3.12 .venv
source .venv/bin/activate
```

**Windows PowerShell:**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

### 3. Install Python dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env`:

**Linux / macOS:**

```bash
cp .env.example .env
```

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set at least:

```dotenv
DJANGO_SECRET_KEY=generate-a-long-random-secret
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DB_ENGINE=postgresql
DB_NAME=brightloop
DB_USER=brightloop_app
DB_PASSWORD=your-local-database-password
DB_HOST=127.0.0.1
DB_PORT=5432
```

The settings loader reads `.env` from the project root. Keep `.env` private; never commit real database passwords, Django secret keys or email credentials. `DJANGO_DEBUG=True` is for local development only.

### 5. Apply the committed database migrations

The repository already includes the initial and follow-up migration files for the application models. A normal checkout should **apply** these migrations rather than regenerate them:

```bash
python manage.py migrate
python manage.py showmigrations
```

Do not run `makemigrations` as part of routine setup. Use it only when you intentionally change Django models and need to create a new migration.

### 6. Create an administrator and start the application

Either create your own administrator:

```bash
python manage.py createsuperuser
```

Or load the development demo accounts and sample data using the command in [Demo data](#demo-data).

Start the local server:

```bash
python manage.py runserver
```

Open these local URLs:

- Web application: <http://127.0.0.1:8000/>
- Django administration: <http://127.0.0.1:8000/admin/>
- API index: <http://127.0.0.1:8000/api/v1/>

## Run and test

With the virtual environment activated:

```bash
python manage.py check
python manage.py check --database default
python manage.py test
```

The test suite covers account registration and permissions, catalogue and subscription behaviour, quotation conversion, billing calculations, invoice/payment workflows, and customer data ownership. Run the complete suite after changing shared models, services, permissions or URL configuration.

## Demo data

The repository includes a development-only management command:

```bash
python manage.py seed_demo
```

It creates sample records when they do not already exist:

- Administrator: `admin@brightloop.local`
- Staff user: `staff@brightloop.local`
- Customer: `customer@brightloop.local`
- Customer profile: Demo Retail Pvt Ltd
- A sample tax rule, product, product variant and monthly plan
- A quotation template and an active subscription with a line item

The demo password is read from `DEMO_PASSWORD` in `.env`. If it is not set, the command's development fallback is `BrightloopDemo!2026`. Use the same password for the three demo accounts. These credentials are for a local demonstration only; do not use them in a shared or production environment. The command does not generate an invoice. Run billing manually after the sample subscription is available.

## Main web pages

The main web interface is available through these routes after signing in where required:

| Route | Purpose |
|---|---|
| `/` | Role-aware dashboard / overview |
| `/accounts/register/` | Customer registration |
| `/accounts/login/` | Sign in |
| `/accounts/profile/` | View and update the signed-in user's own profile |
| `/accounts/password-reset/` | Password-reset flow |
| `/catalog/products/` | Product and variant listing / creation |
| `/catalog/plans/` | Subscription plan listing / creation |
| `/subscriptions/` | Subscription and quotation overview; customer data is scoped to the signed-in customer |
| `/subscriptions/<id>/` | Subscription details and allowed lifecycle controls |
| `/subscriptions/quotations/new/` | Staff quotation builder |
| `/billing/invoices/` | Invoice list; customers see only their own invoices |
| `/billing/invoices/<id>/` | Invoice detail; customers can access only invoices they own |
| `/billing/invoices/<id>/print/` | Print-friendly invoice with browser Print / Save PDF |
| `/billing/discounts/` | Discount-rule management for internal users |
| `/finance/` | Finance dashboard for staff and administrators |
| `/admin/` | Django administration for authorized admin users |

Quotation templates and some lower-level catalogue records can also be managed through the API and Django Admin. The browser quotation builder creates a custom quotation from the selected customer, plan and product line.

## API overview

API routes are prefixed with `/api/v1/`. The API uses Django REST Framework **session authentication**. Public registration and login are available; other routes require authentication and role-appropriate permissions. Browser-based unsafe requests must include a valid CSRF token.

| Method | Endpoint | Purpose / access |
|---|---|---|
| `POST` | `/auth/register/` | Public customer registration; the role is fixed to CUSTOMER |
| `POST` | `/auth/login/` | Authenticate and create a session |
| `POST` | `/auth/logout/` | End the authenticated session |
| `GET` | `/auth/me/` | Retrieve the current user |
| `GET`, `PATCH` | `/auth/profile/` | Read/update the current user's own profile fields |
| `POST` | `/staff/` | Administrator creates a staff account |
| `GET` | `/customers/` | Search customer profiles; internal access |
| `GET`, `POST` and detail operations | `/products/` | Product API; write access is restricted |
| `GET`, `POST` and detail operations | `/variants/` | Product-variant API; write access is restricted |
| `GET`, `POST` and detail operations | `/taxes/` | Tax API; write access is restricted |
| `GET`, `POST` and detail operations | `/plans/` | Subscription-plan API; write access is restricted |
| `GET`, `POST` and detail operations | `/quotation-templates/` | Quotation-template API; administrator access |
| `GET`, `POST` and detail operations | `/quotations/` | Create/list/retrieve quotations; customer list/retrieve results are scoped to the current customer |
| `POST` | `/quotations/{id}/convert/` | Convert an eligible quotation into a subscription |
| `GET`, `POST`, `PUT`, `PATCH` | `/subscriptions/` | Subscription API; customer reads are scoped to owned records; internal users manage records |
| `POST` | `/subscriptions/{id}/transition/` | Apply an allowed lifecycle action to an accessible subscription |
| `GET` | `/me/subscriptions/` | List the authenticated customer's own subscriptions |
| `POST` | `/billing/run/` | Run recurring billing; internal users only |
| `GET` | `/invoices/` | List/retrieve invoices; customer results are scoped to the current customer |
| `POST` | `/invoices/{id}/confirm/` | Confirm a draft invoice; internal users only |
| `POST` | `/invoices/{id}/cancel/` | Cancel an eligible invoice; internal users only |
| `POST` | `/invoices/{id}/send/` | Record the invoice send timestamp; the API action does not send email |
| `POST` | `/invoices/{id}/payments/` | Record a payment; internal users only |
| `GET` | `/me/invoices/` | List the authenticated customer's own invoices |
| `GET`, `POST` and detail operations | `/discount-rules/` | Discount-rule API; administrator access |
| `GET` | `/dashboard/summary/` | Finance summary; internal users only |

The router exposes standard detail routes where supported. Consult the serializers and [docs/API_EXAMPLES.md](docs/API_EXAMPLES.md) for request fields and example payloads.

## Typical end-to-end workflow

A representative staff-led subscription and billing flow is:

1. Register a customer or use the local demo customer.
2. Create/activate the tax, product, optional variant and subscription plan records.
3. Create a quotation for the customer using the quotation builder or a quotation template.
4. Convert an eligible quotation into a subscription.
5. Confirm and activate the subscription.
6. Trigger a manual billing run. The service processes subscriptions whose next billing date is due.
7. Open the generated draft invoice and confirm it.
8. Record a partial payment, then record the remaining balance.
9. Verify the invoice status, balance due and finance dashboard totals.
10. Run billing again and verify that the same subscription period is not billed twice.
11. Sign in as a different customer and verify that the first customer's subscription and invoice records are not visible.

The demo-data command creates an active subscription, but it does not create an invoice. A billing run is needed to generate one when the subscription is due.

## Business rules and data integrity

- `Plan.price` is the recurring base fee. Subscription product lines are additional billable items.
- A subscription stores a plan-price snapshot so later plan-price edits do not silently rewrite the agreed subscription recurring price.
- Direct subscription line prices are derived server-side from product sale price plus the selected variant adjustment. Quotation conversion preserves the quoted line prices.
- Billing is manually triggered in this implementation; no background scheduler is configured.
- Billing uses database transactions and row-level locking. A database uniqueness constraint prevents duplicate invoices for the same subscription and billing period.
- Monthly/yearly billing dates use calendar-aware calculations and clamp to the last valid day of the target month.
- Invoice lines snapshot descriptions, prices, tax rates and discounts so later catalogue edits do not rewrite historical invoice amounts.
- One eligible discount rule is applied per invoice; discount stacking is not implemented.
- Tax is exclusive and calculated after the applicable discount.
- Partial payments are supported. An invoice is paid when its outstanding balance reaches zero.
- Payments are recorded by an internal user against a confirmed invoice; no external payment gateway is integrated.

## Current implementation boundaries

Brightloop is a functional hackathon/demo application, not a fully automated production billing platform. Keep these boundaries in mind:

- Recurring billing is started manually by staff/admin through the web interface or API. There is no scheduled/background billing worker.
- No external payment gateway is connected. Payments are recorded manually by an authorized internal user.
- The invoice print page uses the browser's Print / Save PDF function; the server does not generate a PDF file.
- The HTML invoice send action makes a best-effort email attempt through Django's configured email backend. Configure and test SMTP before relying on delivery. The API send action only records the send timestamp.
- Quotation templates and some catalogue/tax administration are handled through Django Admin and the API; not every model has a dedicated CRUD page.
- The application uses DRF session authentication; a JWT/OAuth authentication flow is not included.

## Security and deployment notes

The included settings are designed for local development. Before any public deployment:

- Set a strong, private `DJANGO_SECRET_KEY`.
- Set `DJANGO_DEBUG=False` and explicitly configure `DJANGO_ALLOWED_HOSTS`.
- Configure HTTPS, secure cookies, CSRF trusted origins and appropriate HSTS settings at the application/proxy boundary.
- Configure and verify SMTP if email delivery is required.
- Use a production PostgreSQL instance with restricted network access, backups and appropriate credentials.
- Configure static-file serving, logging, monitoring and database backups.
- Do not deploy with demo accounts or the development demo password.

Never commit `.env`, database passwords, API secrets or production credentials.

## Further documentation

- [Database schema overview](docs/SCHEMA_OVERVIEW.md)
- [API request examples](docs/API_EXAMPLES.md)
- [Arch Linux setup](docs/SETUP_ARCH_LINUX.md)
- [Windows setup](docs/SETUP_WINDOWS.md)
- [Team task cards / original work allocation](docs/TEAM_TASK_CARDS.md)
