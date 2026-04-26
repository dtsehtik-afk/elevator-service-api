"""Stripe billing — subscriptions per tenant."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_superadmin
from app.config import get_settings
from app.database import get_db
from app.models.tenant import Tenant

router = APIRouter(prefix="/billing", tags=["Billing"])


PLAN_PRICES = {
    # Stripe price IDs — set these in .env or swap to real IDs after creating products in Stripe
    "BASIC": "price_basic_monthly",
    "PRO": "price_pro_monthly",
    "ENTERPRISE": "price_enterprise_monthly",
}


class CreateSubscriptionRequest(BaseModel):
    tenant_id: uuid.UUID
    plan: str   # BASIC | PRO | ENTERPRISE
    payment_method_id: str  # from Stripe.js on the frontend


class SubscriptionOut(BaseModel):
    tenant_id: uuid.UUID
    stripe_customer_id: str
    stripe_subscription_id: str
    plan: str
    status: str


@router.post("/subscribe", response_model=SubscriptionOut)
def create_subscription(
    body: CreateSubscriptionRequest,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Create or update Stripe subscription for a tenant."""
    from app.services.stripe_service import create_or_update_subscription

    if body.plan not in PLAN_PRICES:
        raise HTTPException(status_code=422, detail=f"Unknown plan: {body.plan}")

    tenant = db.get(Tenant, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    result = create_or_update_subscription(
        tenant=tenant,
        plan=body.plan,
        price_id=PLAN_PRICES[body.plan],
        payment_method_id=body.payment_method_id,
    )

    tenant.stripe_customer_id = result["customer_id"]
    tenant.stripe_subscription_id = result["subscription_id"]
    tenant.plan = body.plan
    tenant.billing_active = True
    db.commit()

    return SubscriptionOut(
        tenant_id=body.tenant_id,
        stripe_customer_id=result["customer_id"],
        stripe_subscription_id=result["subscription_id"],
        plan=body.plan,
        status=result["status"],
    )


@router.delete("/{tenant_id}/cancel")
def cancel_subscription(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Cancel Stripe subscription at period end."""
    from app.services.stripe_service import cancel_subscription as _cancel

    tenant = db.get(Tenant, tenant_id)
    if not tenant or not tenant.stripe_subscription_id:
        raise HTTPException(status_code=404, detail="No active subscription")

    _cancel(tenant.stripe_subscription_id)
    tenant.billing_active = False
    db.commit()
    return {"cancelled": True}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    """Handle Stripe webhook events (payment success, cancellation, etc.)."""
    import stripe
    settings = get_settings()
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    _handle_stripe_event(event, db)
    return {"received": True}


def _handle_stripe_event(event: dict, db: Session):
    event_type = event["type"]

    if event_type == "invoice.payment_succeeded":
        sub_id = event["data"]["object"].get("subscription")
        if sub_id:
            tenant = db.query(Tenant).filter_by(stripe_subscription_id=sub_id).first()
            if tenant:
                tenant.billing_active = True
                db.commit()

    elif event_type in ("customer.subscription.deleted", "invoice.payment_failed"):
        sub_id = (
            event["data"]["object"].get("id")
            or event["data"]["object"].get("subscription")
        )
        if sub_id:
            tenant = db.query(Tenant).filter_by(stripe_subscription_id=sub_id).first()
            if tenant:
                tenant.billing_active = False
                tenant.status = "SUSPENDED"
                db.commit()
