# Team task cards — work in parallel after setup

## A — accounts and integration
- Run first `makemigrations` for all apps on the agreed branch and commit initial migrations.
- Test email normalization, password policy, customer registration, session login/logout and password reset email output.
- Add role tests proving only ADMIN can create STAFF and customers cannot see other customers' data.
- Add UI polish to login/register and integrate app routes into root config without taking over B/C files.
- Coordinate all merges and run checks after each merge.

## B — catalogue, quotations and subscriptions
- Complete admin workflows for Product, ProductVariant, Tax, Plan and QuotationTemplate (including inline lines).
- Build usable pages/forms for products, variants, plans, quotations and subscriptions.
- Test variant pricing, plan minimum quantity and availability dates.
- Test quote validity and quote-to-subscription conversion.
- Test all lifecycle actions and plan restrictions for pause, early close and renewal.
- Confirm model/API changes with C before changing shared fields.

## C — billing and finance
- Complete discount rule screens and product-scope selection.
- Test invoice generation and repeated billing; no duplicate invoice per subscription/period.
- Test monthly/yearly boundary dates, discounts/limits, plan tax + line tax, rounding and snapshot stability.
- Test invoice confirm/cancel/send flow and partial/full/overpayment handling.
- Build finance views/filters and add query optimization only where measurements justify it.
- PDF/email can be deferred unless end-to-end billing is already stable.

## Shared test path
1. Create customer.
2. Create Tax, Product, Variant and Plan.
3. Create QuotationTemplate with one or more lines.
4. Create a Quotation from the template.
5. Convert to Subscription.
6. Transition subscription: `confirm` → `activate`.
7. Run `POST /api/v1/billing/run/`.
8. Confirm the Draft invoice.
9. Record a partial payment, then the final balance.
10. Confirm invoice status becomes PAID and dashboard revenue changes.
11. Repeat billing and confirm no duplicate invoice is created.
12. Log in as a different customer and confirm first customer's records are inaccessible.
