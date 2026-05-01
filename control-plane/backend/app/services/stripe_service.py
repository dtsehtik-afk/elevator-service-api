"""Stripe billing service."""

import logging

import stripe

from app.config import get_settings

logger = logging.getLogger(__name__)


def _stripe():
    stripe.api_key = get_settings().stripe_secret_key
    return stripe


def create_or_update_subscription(tenant, plan: str, price_id: str, payment_method_id: str) -> dict:
    """Create a Stripe customer + subscription, or update the existing one."""
    s = _stripe()

    # Create or reuse customer
    if tenant.stripe_customer_id:
        customer_id = tenant.stripe_customer_id
    else:
        customer = s.Customer.create(
            email=tenant.contact_email,
            name=tenant.name,
            metadata={"tenant_slug": tenant.slug},
        )
        customer_id = customer.id

    # Attach payment method
    s.PaymentMethod.attach(payment_method_id, customer=customer_id)
    s.Customer.modify(
        customer_id,
        invoice_settings={"default_payment_method": payment_method_id},
    )

    # Create or upgrade subscription
    if tenant.stripe_subscription_id:
        sub = s.Subscription.retrieve(tenant.stripe_subscription_id)
        updated = s.Subscription.modify(
            tenant.stripe_subscription_id,
            items=[{"id": sub["items"]["data"][0]["id"], "price": price_id}],
            proration_behavior="always_invoice",
        )
        return {
            "customer_id": customer_id,
            "subscription_id": updated.id,
            "status": updated.status,
        }
    else:
        sub = s.Subscription.create(
            customer=customer_id,
            items=[{"price": price_id}],
            expand=["latest_invoice.payment_intent"],
        )
        return {
            "customer_id": customer_id,
            "subscription_id": sub.id,
            "status": sub.status,
        }


def cancel_subscription(subscription_id: str) -> None:
    """Cancel at end of billing period."""
    _stripe().Subscription.modify(subscription_id, cancel_at_period_end=True)
    logger.info("Subscription %s set to cancel at period end", subscription_id)


def get_upcoming_invoice(subscription_id: str) -> dict | None:
    """Return next invoice details."""
    try:
        inv = _stripe().Invoice.upcoming(subscription=subscription_id)
        return {
            "amount_due": inv.amount_due / 100,
            "currency": inv.currency,
            "period_end": inv.period_end,
        }
    except Exception:
        return None
