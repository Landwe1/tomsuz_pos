import random
from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from sales.models import Store, Sale, SaleItem
from products.models import Product, Category


class Command(BaseCommand):
    help = "Seeds 90 days of synthetic sales transactions to test merchant credit scoring."

    def handle(self, *args, **kwargs):
        store = Store.objects.first()
        if not store:
            self.stdout.write(self.style.ERROR("No store found in database. Please create a Store first."))
            return

        self.stdout.write(self.style.SUCCESS(f"Seeding sales history for store: '{store.name}'..."))

        # 1. Fetch or create a default cashier/user for the store
        cashier = store.owner

        # 2. Fetch or create a Category & Product matching your actual Product model fields
        category, _ = Category.objects.get_or_create(
            store=store,
            name="General Goods"
        )

        product = Product.objects.filter(store=store).first()
        if not product:
            product = Product.objects.create(
                store=store,
                category=category,
                name="Credit Test Item",
                unit_type="PC",
                buying_price=Decimal("50.00"),
                selling_price=Decimal("100.00"),
                min_price=Decimal("80.00"),
                stock_quantity=Decimal("5000.00"),
            )
            self.stdout.write(f"Created sample test product: {product.name}")
        else:
            # Ensure the existing product has ample stock for seeding without throwing ValueError
            if product.stock_quantity < Decimal("1000.00"):
                product.stock_quantity += Decimal("5000.00")
                product.save(update_fields=['stock_quantity'])

        now = timezone.now()
        sales_created = 0
        items_created = 0

        # 3. Simulate 90 days of store activity
        for day_offset in range(90):
            # Simulate closed days (~15% chance of no sales on a given day)
            if random.random() < 0.15:
                continue

            sale_date = now - timedelta(days=day_offset)
            daily_transactions = random.randint(2, 8)

            for _ in range(daily_transactions):
                qty = Decimal(str(random.randint(1, 5)))
                unit_price = product.selling_price
                subtotal = qty * unit_price

                # Create master Sale instance
                sale = Sale.objects.create(
                    store=store,
                    cashier=cashier,
                    amount_paid=subtotal,
                    change_due=Decimal("0.00"),
                    payment_method=random.choice(['CASH', 'MOMO', 'CREDIT']),
                )

                # Explicitly override auto_now_add timestamp to build realistic 90-day history
                Sale.objects.filter(pk=sale.pk).update(timestamp=sale_date)

                # Create SaleItem line entry
                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=qty,
                    unit_price=unit_price,
                )

                sales_created += 1
                items_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully generated {sales_created} sales and {items_created} line items across 90 days."
            )
        )
