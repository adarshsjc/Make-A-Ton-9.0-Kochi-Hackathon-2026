# Brightloop — Subscription Management System

Brightloop is a web application for managing a subscription business: customers, products, plans, quotations, subscriptions, recurring invoices, discounts, payments and finance summaries.

The application is built as a **Django modular monolith** backed by **PostgreSQL**. It uses Django templates for the web interface and Django REST Framework for structured API access.

## Technology stack

| Component | Version / choice |
|---|---|
| Python | 3.12.x |
| Django | 5.2.18 LTS |
| Django REST Framework | 3.18.1 |
| django-filter | 26.2 |
| PostgreSQL | 18.x |
| Psycopg | 3.3.6 |
| Configuration | `python-dotenv` |
| Frontend | Django templates, HTML, CSS and JavaScript |
| UI styling | Local CSS; no frontend build step |

Dependency versions are pinned in `requirements.txt`.

## Main capabilities

- **Accounts and access control:** customer registration, login/logout, password-reset views, staff creation by administrators, and role-aware access.
- **Product catalogue:** products, product variants, taxes and subscription plans.
- **Quotations:** reusable quotation templates, quotation creation and conversion to subscriptions.
- **Subscription lifecycle:** draft, quotation, confirmed, active, paused and closed states, with validated lifecycle actions.
- **Recurring billing:** manually triggered billing for subscriptions that are due, with duplicate-period protection.
- **Invoices and payments:** invoice confirmation/cancellation, payment recording and support for partial payments.
- **Discounts:** fixed-amount or percentage rules with eligibility dates and usage limits.
- **Finance summary:** database-backed subscription, payment, outstanding and overdue figures.
- **Customer access:** customers can view their own subscriptions and invoices, subject to server-side query scoping.

The current web interface includes account pages and a dashboard. Most catalogue, quotation, subscription and finance-management operations are exposed through the API and Django admin; dedicated user-facing CRUD screens for every resource are not yet included.

## Project structure

```text
brightloop/
├── accounts/        Custom user model, customer profile and authentication APIs
├── catalog/         Products, variants, taxes and plans
├── subscriptions/   Quotation templates, quotations and subscriptions
├── billing/         Discount rules, invoices, invoice lines and payments
├── dashboard/       Dashboard views, aggregates and demo-data command
├── common/          Shared permissions and numbering helpers
├── config/           Django settings and root URL configuration
├── docs/             Schema, API examples and platform setup notes
├── scripts/          Platform-specific setup helpers
├── templates/        Shared and account/dashboard templates
├── static/           Local CSS assets
├── manage.py
├── requirements.txt
└── .env.example
```

## Requirements

- Python 3.12
- PostgreSQL 18.x (recommended for the configured database backend)
- Git

Platform-specific setup notes are available in [docs/SETUP_ARCH_LINUX.md](docs/SETUP_ARCH_LINUX.md) and [docs/SETUP_WINDOWS.md](docs/SETUP_WINDOWS.md).

## Local installation

The following steps are the same in principle on Linux and Windows. Use the appropriate virtual-environment activation command for your shell.

### 1. Create a PostgreSQL database

Connect to PostgreSQL as an administrator and create an application role and database. Replace the example password with a unique local password:

```sql
CREATE ROLE brightloop_app WITH LOGIN PASSWORD 'replace-with-a-local-password';
CREATE DATABASE brightloop OWNER brightloop_app;
```

The application connects to PostgreSQL through `127.0.0.1:5432` by default. Each installation should use its own local database; do not expose the database server publicly for ordinary development.

### 2. Create a Python virtual environment

**Linux:**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell:**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and set the local database password and a private Django secret key.

**Linux:**

```bash
cp .env.example .env
```

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

The `.env` file is excluded from Git. Never commit database passwords, secret keys or real email credentials.

### 5. Create and apply database migrations

This repository contains the Django model definitions but does not include generated initial application migrations. Generate the initial migration files from the current models, then apply them:

```bash
python manage.py makemigrations accounts catalog subscriptions billing
python manage.py migrate
```

After initial migrations have been created, keep the generated migration files under version control. On an existing checkout that already contains the migration files, apply them with `python manage.py migrate`; do not regenerate them unnecessarily.

### 6. Check and run the application

```bash
python manage.py check
python manage.py test
python manage.py createsuperuser
python manage.py runserver
```

Open:

- Web application: <http://127.0.0.1:8000/>
- Django admin: <http://127.0.0.1:8000/admin/>
- API index: <http://127.0.0.1:8000/api/v1/>

## Demo data

After applying migrations, create sample records with:

```bash
python manage.py seed_demo
```

The command creates development-only customer, staff and administrator accounts and related sample catalogue/subscription data. Their credentials are controlled by the local `DEMO_PASSWORD` environment variable. Change the demo password before running the command in any environment that other people can access. Do not use demo accounts in production.

The billing run can be triggered by an authenticated staff or administrator using `POST /api/v1/billing/run/`. Newly generated invoices are drafts; confirm an invoice before recording a payment.

## API overview

All API routes are prefixed with `/api/v1/`. The API uses Django REST Framework session authentication. Unsafe requests made from a browser session must include a valid CSRF token.

| Method | Endpoint | Purpose / access |
|---|---|---|
| `POST` | `/auth/register/` | Public customer registration |
| `POST` | `/auth/login/` | Create an authenticated session |
| `POST` | `/auth/logout/` | End the current session |
| `GET` | `/auth/me/` | Retrieve the current authenticated user |
| `POST` | `/staff/` | Administrator creates a staff account |
| `GET` | `/customers/` | Search customer profiles (internal access) |
| `GET`, `POST` | `/products/` | List and manage products; writes are administrator-restricted |
| `GET`, `POST` | `/variants/` | List and manage product variants; writes are administrator-restricted |
| `GET`, `POST` | `/taxes/` | List and manage tax rules; writes are administrator-restricted |
| `GET`, `POST` | `/plans/` | List and manage subscription plans; writes are administrator-restricted |
| `GET`, `POST` | `/quotation-templates/` | Manage quotation templates (administrator) |
| `GET`, `POST` | `/quotations/` | List/create quotations (internal users); customers are scoped to their own records when listing |
| `POST` | `/quotations/{id}/convert/` | Convert a valid quotation into a subscription |
| `GET`, `POST` | `/subscriptions/` | List/create subscriptions (customers can only view their own records) |
| `POST` | `/subscriptions/{id}/transition/` | Apply an allowed subscription lifecycle action |
| `GET` | `/me/subscriptions/` | List the authenticated customer's subscriptions |
| `POST` | `/billing/run/` | Generate invoices for due subscriptions (internal users) |
| `GET` | `/invoices/` | List/retrieve invoices; customer results are scoped to the current customer |
| `POST` | `/invoices/{id}/confirm/` | Confirm a draft invoice (internal users) |
| `POST` | `/invoices/{id}/cancel/` | Cancel an eligible unpaid invoice (internal users) |
| `POST` | `/invoices/{id}/send/` | Record an invoice send timestamp (internal users; does not send email) |
| `POST` | `/invoices/{id}/payments/` | Record a payment against an invoice (internal users) |
| `GET` | `/me/invoices/` | List the authenticated customer's invoices |
| `GET`, `POST` | `/discount-rules/` | List/create discount rules (administrator) |
| `GET` | `/dashboard/summary/` | Retrieve finance summary data (internal users) |

The router also exposes standard detail routes for resources managed through viewsets. Refer to the viewset serializers for accepted request fields and response schemas. Example requests are documented in [docs/API_EXAMPLES.md](docs/API_EXAMPLES.md).

## Subscription lifecycle

The subscription transition endpoint accepts an action in a JSON request body. For example:

```json
{"action": "send_quotation"}
```

Supported actions are `send_quotation`, `confirm`, `activate`, `pause`, `resume`, `close` and `renew`. The service layer validates whether a requested transition is allowed and checks applicable plan restrictions.

## Billing rules and data integrity

- Billing is manually triggered for this implementation; a background scheduler is not required.
- An invoice is unique per subscription and billing period, with a database constraint to prevent duplicate billing for the same period.
- Invoice generation uses database transactions and row-level locking.
- Monthly and yearly billing dates are calculated using calendar-aware date handling, including clamping to the last valid day of a target month.
- `Plan.price` is the recurring base fee. Subscription product lines are additional billable items.
- Direct subscription line prices are derived on the server from the product sale price and selected variant adjustment. Quotation conversion preserves quoted line prices.
- Invoice lines snapshot relevant descriptions, prices, tax rates and discount values so later catalogue edits do not rewrite historical invoice amounts.
- One eligible discount rule is applied per invoice. Discount stacking is not implemented.
- Tax is exclusive and calculated after the applicable discount.
- Partial payments are supported. An invoice is marked paid when its outstanding balance reaches zero.
- Payments can only be recorded against confirmed invoices.

## Current implementation boundaries

The following capabilities are not implemented in the current codebase and should not be assumed to work:

- Actual outbound invoice email delivery. The invoice `send` action currently records a timestamp only.
- Invoice PDF generation or a dedicated print layout.
- A scheduled/background billing worker. Billing is started through the API endpoint.
- Dedicated CRUD pages for every catalogue, quotation, subscription and finance resource. The corresponding API and Django admin are available for much of this management functionality.
- Advanced dashboard filtering and extensive automated coverage for all authorization, billing and concurrency edge cases.

## Security and deployment notes

The included configuration is intended for local development. Before deployment, configure a strong `DJANGO_SECRET_KEY`, set `DJANGO_DEBUG=False`, define the correct `DJANGO_ALLOWED_HOSTS`, configure HTTPS and secure cookies, use production-grade email settings, and review database access, logging, backup and static-file serving. Never deploy with demo credentials or development secrets.

## Further documentation

- [Database schema overview](docs/SCHEMA_OVERVIEW.md)
- [API request examples](docs/API_EXAMPLES.md)
- [Arch Linux setup](docs/SETUP_ARCH_LINUX.md)
- [Windows setup](docs/SETUP_WINDOWS.md)
