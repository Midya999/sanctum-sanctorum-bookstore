"""Library loan operations: borrowing and returning books."""
from datetime import datetime, timedelta
from math import ceil
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book, Loan, Member, MemberTier
from app.schemas import LoanCreate, LoanOut, LoanStatus

# Maximum concurrent unreturned loans per tier (None = unlimited).
TIER_LOAN_LIMIT: Dict[str, Optional[int]] = {
    MemberTier.APPRENTICE.value: 1,
    MemberTier.ADEPT.value: 3,
    MemberTier.MASTER.value: 5,
    MemberTier.SUPREME.value: None,
}

LOAN_PERIOD = timedelta(days=14)
LATE_FEE_PER_DAY_CENTS = 25


def loan_status(loan: Loan, now: datetime) -> LoanStatus:
    """``returned`` if returned; else ``overdue`` if now > due_at; else ``active``."""
    if loan.returned_at is not None:
        return "returned"

    if now > loan.due_at:
        return "overdue"

    return "active"

def to_loan_out(loan: Loan, now: datetime) -> LoanOut:
    """Serialize a loan, computing its status at read time."""
    return LoanOut(
        id=loan.id,
        member_id=loan.member_id,
        book_id=loan.book_id,
        borrowed_at=loan.borrowed_at,
        due_at=loan.due_at,
        returned_at=loan.returned_at,
        late_fee_cents=loan.late_fee_cents,
        status=loan_status(loan, now),
    )


def calculate_late_fee(
    due_at: datetime,
    returned_at: datetime,
    price_cents: int,
) -> int:
    """25 cents per started day late, capped at the book's price; 0 if not late."""
    if returned_at <= due_at:
        return 0

    seconds_late = (returned_at - due_at).total_seconds()
    days_late = ceil(seconds_late / (24 * 60 * 60))

    fee = days_late * LATE_FEE_PER_DAY_CENTS

    return min(fee, price_cents)

def create_loan(db: Session, data: LoanCreate, now: datetime) -> LoanOut:
    """Borrow a book for 14 days."""

    # 1. Check that the member exists.
    member = db.get(Member, data.member_id)

    if member is None:
        raise HTTPException(
            status_code=404,
            detail="Member not found",
        )

    # 2. Check that the book exists.
    book = db.get(Book, data.book_id)

    if book is None:
        raise HTTPException(
            status_code=404,
            detail="Book not found",
        )

    # 3. Restricted books require MASTER or higher.
    tier_rank = {
        MemberTier.APPRENTICE.value: 0,
        MemberTier.ADEPT.value: 1,
        MemberTier.MASTER.value: 2,
        MemberTier.SUPREME.value: 3,
    }

    if book.restricted and tier_rank[member.tier] < tier_rank[
        MemberTier.MASTER.value
    ]:
        raise HTTPException(
            status_code=403,
            detail="Restricted books require tier 'master' or higher",
        )

    # Get this member's currently unreturned loans.
    active_loans = list(
        db.scalars(
            select(Loan).where(
                Loan.member_id == member.id,
                Loan.returned_at.is_(None),
            )
        )
    )

    # 4. An overdue loan prevents a new loan.
    if any(loan_status(loan, now) == "overdue" for loan in active_loans):
        raise HTTPException(
            status_code=409,
            detail="Member has an overdue loan",
        )

    # 5. The same book cannot be borrowed twice at the same time.
    if any(loan.book_id == book.id for loan in active_loans):
        raise HTTPException(
            status_code=409,
            detail="Member already has an unreturned loan for this book",
        )

    # 6. Check the member's tier loan limit.
    loan_limit = TIER_LOAN_LIMIT[member.tier]

    if loan_limit is not None and len(active_loans) >= loan_limit:
        raise HTTPException(
            status_code=409,
            detail="Member has reached the loan limit",
        )

    # 7. Check stock.
    if book.stock <= 0:
        raise HTTPException(
            status_code=409,
            detail="Book is out of stock",
        )

    # Create the loan.
    borrowed_at = now
    due_at = now + LOAN_PERIOD

    loan = Loan(
        member_id=member.id,
        book_id=book.id,
        borrowed_at=borrowed_at,
        due_at=due_at,
        returned_at=None,
        late_fee_cents=0,
    )

    # Reserve one copy of the book.
    book.stock -= 1

    db.add(loan)
    db.commit()
    db.refresh(loan)

    return to_loan_out(loan, now)
def get_loan(db: Session, loan_id: int, now: datetime) -> LoanOut:
    """Return a loan by id, or raise 404."""
    loan = db.get(Loan, loan_id)

    if loan is None:
        raise HTTPException(
            status_code=404,
            detail="Loan not found",
        )

    return to_loan_out(loan, now)
def return_loan(db: Session, loan_id: int, now: datetime) -> LoanOut:
    """Return a borrowed book."""

    loan = db.get(Loan, loan_id)

    if loan is None:
        raise HTTPException(
            status_code=404,
            detail="Loan not found",
        )

    if loan.returned_at is not None:
        raise HTTPException(
            status_code=409,
            detail="Loan has already been returned",
        )

    book = db.get(Book, loan.book_id)

    loan.returned_at = now

    loan.late_fee_cents = calculate_late_fee(
        loan.due_at,
        now,
        book.price_cents,
    )

    # Return the physical book to stock.
    book.stock += 1

    db.commit()
    db.refresh(loan)

    return to_loan_out(loan, now)
def list_member_loans(
    db: Session,
    member_id: int,
    now: datetime,
    status: Optional[LoanStatus] = None,
) -> List[LoanOut]:
    """A member's loans ordered by id, optionally filtered by computed status."""

    member = db.get(Member, member_id)

    if member is None:
        raise HTTPException(
            status_code=404,
            detail="Member not found",
        )

    loans = list(
        db.scalars(
            select(Loan)
            .where(Loan.member_id == member_id)
            .order_by(Loan.id)
        )
    )

    result = [to_loan_out(loan, now) for loan in loans]

    if status is not None:
        result = [
            loan
            for loan in result
            if loan.status == status
        ]

    return result