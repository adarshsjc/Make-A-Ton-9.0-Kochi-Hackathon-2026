# API examples

All API endpoints require a Django session unless explicitly public. For browser-based DRF usage, log in and preserve CSRF cookies/tokens for POST/PATCH/DELETE requests.

## Customer registration

`POST /api/v1/auth/register/`

```json
{
  "email": "customer@example.com",
  "password": "Brightloop!2026",
  "full_name": "Example Customer",
  "phone": "+91 9000000000",
  "company_name": "Example Stores",
  "billing_address": "Kochi, Kerala"
}
```

## Login

`POST /api/v1/auth/login/`

```json
{"email":"customer@example.com","password":"Brightloop!2026"}
```

## Create a subscription (internal staff)

The selected Plan's `price` is the recurring base fee. Product lines are additional items; their unit price is derived on the server from `product.sale_price + variant.price_adjustment`. The optional plan tax and each product-line tax are snapshotted onto the generated invoice.

`POST /api/v1/subscriptions/`

```json
{
  "customer": 3,
  "plan": 1,
  "start_date": "2026-10-31",
  "expiry_date": "2027-10-30",
  "payment_terms_days": 15,
  "notes": "Annual CRM subscription",
  "lines": [
    {"product": 1, "variant": 1, "quantity": 2, "tax": 1}
  ]
}
```

## Transition a subscription

`POST /api/v1/subscriptions/1/transition/`

```json
{"action":"confirm"}
```

Possible sequence for a direct subscription: `confirm` → `activate`. For quote-based flow, create quotation from template, call `/api/v1/quotations/{id}/convert/`, then `confirm` → `activate`.

## Run billing

`POST /api/v1/billing/run/`

No body required. Example shape:

```json
{
  "processed": 1,
  "invoices_created": 1,
  "already_billed": 0,
  "failed": [],
  "failed_count": 0
}
```

## Confirm invoice and record payment

`POST /api/v1/invoices/1/confirm/`

Then:

`POST /api/v1/invoices/1/payments/`

```json
{
  "method": "UPI",
  "amount": "500.00",
  "payment_date": "2026-10-31",
  "note": "First partial payment",
  "reference": "UPI-DEMO-001"
}
```


## Search customers

`GET /api/v1/customers/?search=retail` (internal staff/admin). The response is paginated and can be ordered using `?ordering=company_name`.
