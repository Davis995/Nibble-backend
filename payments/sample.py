from payments.models import Payment, Invoice, Audit
from authentication.models import User, Subscription, Plan
from schools.models import School
from datetime import datetime, date, timedelta
import uuid
import random


def run():
    print("Clearing existing payments data...")
    Audit.objects.all().delete()
    Invoice.objects.all().delete()
    Payment.objects.all().delete()

    print("Creating plans and related entities...")
    enterprise_plan, _ = Plan.objects.get_or_create(
        name="Enterprise Premium",
        use_type="enterprise",
        defaults={
            "total_credits": 10000,
            "max_users": 300,
            "monthly_price": 6000.00
        }
    )

    individual_plan, _ = Plan.objects.get_or_create(
        name="Individual Pro",
        use_type="individual",
        defaults={
            "total_credits": 5000,
            "max_users": 1,
            "monthly_price": 150.00
        }
    )

    print("Creating sample schools...")
    schools_data = [
        {"name": "Nairobi International School", "email": "admin@nairobi-intl.edu"},
        {"name": "Mombasa Academy", "email": "admin@mombasa-academy.edu"},
        {"name": "Kisumu High School", "email": "admin@kisumu-high.edu"},
    ]
    
    schools = []
    subscriptions = []
    for school_data in schools_data:
        school, _ = School.objects.get_or_create(
            name=school_data["name"],
            defaults={"school_email": school_data["email"], "max_students": 300}
        )
        schools.append(school)
        
        subscription, _ = Subscription.objects.get_or_create(
            plan=enterprise_plan,
            organisation=school,
            defaults={
                "max_users": enterprise_plan.max_users,
                "start_credits": enterprise_plan.total_credits,
                "remaining_credits": random.randint(5000, 10000),
                "billing_start_date": date.today(),
                "billing_end_date": date.today() + timedelta(days=30),
                "status": "active"
            }
        )
        subscriptions.append(subscription)

    print("Creating sample users for payments...")
    payers = []
    for idx in range(3):
        user, _ = User.objects.get_or_create(
            email=f"payer{idx+1}@example.com",
            defaults={
                "first_name": f"Payer{idx+1}",
                "last_name": "User",
                "user_type": "enterprise",
                "password": "pass1234"
            }
        )
        payers.append(user)

    print("Creating comprehensive payment records...")
    payment_statuses = ["complete", "pending", "failed", "refunded"]
    payment_methods = ["mpesa", "card", "bank_transfer"]
    
    payments = []
    for idx, (school, subscription) in enumerate(zip(schools, subscriptions)):
        # Create 2-3 payments per school
        for payment_idx in range(random.randint(2, 3)):
            payment = Payment.objects.create(
                payment_type="subscription",
                merchant_reference=f"MERCH{uuid.uuid4().hex[:8].upper()}",
                order_tracking_id=f"ORDER{uuid.uuid4().hex[:8].upper()}",
                organisation=school,
                subscription=subscription,
                user=payers[idx % len(payers)],
                amount=float(enterprise_plan.monthly_price) + random.uniform(-500, 500),
                currency="KES",
                plan=enterprise_plan,
                status=random.choice(payment_statuses),
                paymethod=random.choice(payment_methods),
                payment_method=random.choice(["M-Pesa", "Credit Card", "Bank Transfer"]),
                payer_name=f"{payers[idx % len(payers)].first_name} {payers[idx % len(payers)].last_name}",
                payer_email=payers[idx % len(payers)].email,
                payer_phone=f"+254{random.randint(700000000, 799999999)}"
            )
            payments.append(payment)

    # Create individual user payments
    print("Creating individual user payments...")
    for user in payers:
        payment = Payment.objects.create(
            payment_type="topup",
            merchant_reference=f"MERCH{uuid.uuid4().hex[:8].upper()}",
            organisation=schools[0],
            user=user,
            amount=float(individual_plan.monthly_price),
            currency="KES",
            plan=individual_plan,
            status="complete",
            paymethod="card",
            payment_method="Credit Card",
            payer_name=f"{user.first_name} {user.last_name}",
            payer_email=user.email,
            payer_phone=f"+254{random.randint(700000000, 799999999)}"
        )
        payments.append(payment)

    print("Creating invoices for payments...")
    for payment in payments:
        if payment.status in ["complete", "pending"]:
            invoice = Invoice.objects.create(
                invoice_number=f"INV-{date.today().year}-{payment.id}",
                payment=payment,
                organisation=payment.organisation,
                amount=payment.amount,
                currency=payment.currency,
                status="paid" if payment.status == "complete" else "pending",
                due_date=date.today() + timedelta(days=30),
                paid_at=date.today() if payment.status == "complete" else None
            )

    print("Creating audit logs...")
    audit_actions = ["payment_created", "payment_processed", "invoice_generated", "refund_initiated", "status_updated"]
    for idx, payment in enumerate(payments[:5]):
        Audit.objects.create(
            payment=payment,
            action=random.choice(audit_actions),
            timestamp=datetime.now() - timedelta(days=random.randint(1, 30)),
            details=f"Action performed on payment {payment.id}"
        )

    print("✅ Payments app sample data created successfully!")
    print(f"   - Created {Payment.objects.count()} payments")
    print(f"   - Created {Invoice.objects.count()} invoices")
    print(f"   - Created {Audit.objects.count()} audit logs")
    print(f"   - Created {Subscription.objects.count()} subscriptions")


if __name__ == "__main__":
    run()
