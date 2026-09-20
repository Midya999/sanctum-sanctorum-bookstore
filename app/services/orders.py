"""Order operations: placing, paying and cancelling purchases."""
from datetime import datetime
from typing import Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    Book,
    Member,
    MemberTier,
    Order,
    OrderItem,
    OrderStatus,
)
from app.schemas import OrderCreate

# Percentage discount granted by each membership tier.
TIER_DISCOUNT_PERCENT: Dict[str, int] = {
    MemberTier.APPRENTICE.value: 0,
    MemberTier.ADEPT.value: 5,
    MemberTier.MASTER.value: 10,
    MemberTier.SUPREME.value: 15,
}

# Extra discount when the total quantity across all items reaches the threshold.
BULK_QUANTITY_THRESHOLD = 10
BULK_DISCOUNT_PERCENT = 5


def calculate_discount_percent(member: Member, total_quantity: int) -> int:
    """Tier discount, plus the bulk discount when total quantity >= threshold."""
    discount_percent = TIER_DISCOUNT_PERCENT[member.tier]

    if total_quantity >= BULK_QUANTITY_THRESHOLD:
        discount_percent += BULK_DISCOUNT_PERCENT

    return discount_percent


def create_order(db: Session, data: OrderCreate, now: datetime) -> Order:
    """Place a pending order and reserve stock.

    Checks, in order (422 for empty items / bad quantity / duplicate books is done by the schema):
    1. 404 member not found; 404 any book not found
    2. 403 any book restricted and member tier below master
    3. 409 any book has insufficient stock (all-or-nothing: nothing is changed)
    Then stock is decremented for every item and prices are snapshotted.
    Pricing: discount_cents = subtotal * percent // 100; total = subtotal - discount.
    """
    # TODO:
    # 1. Load the member (404) and every book (404).
    # 2. If any book is restricted, check the member's tier (403).
    # 3. Check stock for every item before changing anything (409).
    # 4. Decrement stock and build OrderItems with the current price as unit_price_cents.
    # 5. Compute subtotal, discount_percent (calculate_discount_percent), discount_cents, total.
    # 6. Save the pending Order with created_at = now and return it.
def create_order(db: Session, data: OrderCreate, now: datetime) -> Order:
    """Place a pending order and reserve stock.

    Checks, in order:
    1. 404 member not found; 404 any book not found
    2. 403 any book restricted and member tier below master
    3. 409 any book has insufficient stock
    """
    # 1. Load the member
    member = db.get(Member, data.member_id)

    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    # 2. Load every book before changing any stock
    books = {}

    for item in data.items:
        book = db.get(Book, item.book_id)

        if book is None:
            raise HTTPException(
                status_code=404,
                detail="Book not found",
            )

        books[item.book_id] = book

    # 3. Check restricted books
    tier_order = {
        MemberTier.APPRENTICE.value: 0,
        MemberTier.ADEPT.value: 1,
        MemberTier.MASTER.value: 2,
        MemberTier.SUPREME.value: 3,
    }

    if any(
        book.restricted
        for book in books.values()
    ):
        if tier_order[member.tier] < tier_order[MemberTier.MASTER.value]:
            raise HTTPException(
                status_code=403,
                detail="Member tier is not allowed to purchase restricted books",
            )

    # 4. Check ALL stock before changing anything
    for item in data.items:
        book = books[item.book_id]

        if book.stock < item.quantity:
            raise HTTPException(
                status_code=409,
                detail="Insufficient stock",
            )

    # 5. Calculate pricing
    subtotal = sum(
        books[item.book_id].price_cents * item.quantity
        for item in data.items
    )

    total_quantity = sum(
        item.quantity
        for item in data.items
    )

    discount_percent = calculate_discount_percent(
        member,
        total_quantity,
    )

    discount_cents = subtotal * discount_percent // 100
    total_cents = subtotal - discount_cents

    # 6. Create the pending order
    order = Order(
        member_id=member.id,
        status=OrderStatus.PENDING.value,
        subtotal_cents=subtotal,
        discount_percent=discount_percent,
        discount_cents=discount_cents,
        total_cents=total_cents,
        created_at=now,
    )

    # 7. Reserve stock and create order items
    for item in data.items:
        book = books[item.book_id]

        book.stock -= item.quantity

        order.items.append(
            OrderItem(
                book_id=book.id,
                quantity=item.quantity,
                unit_price_cents=book.price_cents,
            )
        )

    db.add(order)
    db.commit()
    db.refresh(order)

    return order


def get_order(db: Session, order_id: int) -> Order:
    """Return an order by id, or raise 404."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def pay_order(db: Session, order_id: int) -> Order:
    """Mark a pending order as paid. 404 if missing; 409 if not pending."""
    order = get_order(db, order_id)
    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(status_code=409, detail=f"Cannot pay an order that is {order.status}")
    order.status = OrderStatus.PAID.value
    db.commit()
    db.refresh(order)
    return order


def cancel_order(db: Session, order_id: int) -> Order:
    """Cancel a pending order and restore the reserved stock. 404 if missing; 409 if not pending."""
    order = get_order(db, order_id)

    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel an order that is {order.status}",
        )

    for item in order.items:
        item.book.stock += item.quantity

    order.status = OrderStatus.CANCELLED.value

    db.commit()
    db.refresh(order)

    return order
