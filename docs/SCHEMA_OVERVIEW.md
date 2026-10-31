# Schema overview

## Main relationships

```mermaid
erDiagram
    USER ||--o| CUSTOMER_PROFILE : has
    USER ||--o{ QUOTATION : receives
    USER ||--o{ SUBSCRIPTION : owns
    USER ||--o{ INVOICE : billed
    PRODUCT ||--o{ PRODUCT_VARIANT : has
    PRODUCT ||--o{ QUOTATION_TEMPLATE_LINE : quoted
    PRODUCT ||--o{ SUBSCRIPTION_LINE : subscribed
    PRODUCT ||--o{ INVOICE_LINE : snapshots
    PLAN ||--o{ SUBSCRIPTION : chosen
    PLAN ||--o{ QUOTATION_TEMPLATE : offered
    PLAN ||--o{ QUOTATION_TEMPLATE_LINE : indirectly
    QUOTATION_TEMPLATE ||--o{ QUOTATION_TEMPLATE_LINE : contains
    QUOTATION_TEMPLATE ||--o{ QUOTATION : instantiates
    QUOTATION ||--o| SUBSCRIPTION : converts
    QUOTATION ||--o{ QUOTATION_LINE : snapshots
    SUBSCRIPTION ||--o{ SUBSCRIPTION_LINE : contains
    SUBSCRIPTION ||--o{ INVOICE : generates
    INVOICE ||--o{ INVOICE_LINE : contains
    INVOICE ||--o{ PAYMENT : receives
    DISCOUNT_RULE ||--o{ DISCOUNT_REDEMPTION : used
    INVOICE ||--o{ DISCOUNT_REDEMPTION : records
    TAX ||--o{ PLAN : taxes
    TAX ||--o{ SUBSCRIPTION_LINE : taxes
    TAX ||--o{ QUOTATION_TEMPLATE_LINE : taxes
```

## Billing interpretation used by this starter

- `Plan.price` is the recurring base fee and is included once in each billing-period invoice. `Plan.tax` is optional.
- `SubscriptionLine` represents additional billable products/add-ons. Their direct-subscription unit price is derived from product sale price plus variant adjustment.
- Quotation template lines can contain agreed/negotiated unit prices; conversion preserves those prices.
- Invoice lines are immutable price/tax/discount snapshots. Later catalogue edits do not rewrite historical invoices.
- One best eligible discount is applied per invoice; discount stacking is intentionally excluded from the hackathon baseline.

## Ownership boundaries

- `accounts`: User and customer profile. Other apps FK to `settings.AUTH_USER_MODEL`.
- `catalog`: Product, ProductVariant, Tax, Plan.
- `subscriptions`: QuotationTemplate, Quotation, Subscription and line items.
- `billing`: DiscountRule, Invoice, InvoiceLine, DiscountRedemption, Payment.
- `dashboard`: read-only aggregates over the other apps.
