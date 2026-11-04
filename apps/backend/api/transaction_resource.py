"""FastAPI router for the /transactions endpoints (create + read only)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from transactions import service
from transactions.models import Transaction, TransactionCreate

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/generate", response_model=list[Transaction], status_code=201)
def generate_transactions() -> list[Transaction]:
    try:
        return service.generate()
    except service.NoEligibleAccountsError:
        raise HTTPException(status_code=409, detail="No active accounts available")


@router.post("", response_model=Transaction, status_code=201)
def create_transaction(data: TransactionCreate) -> Transaction:
    return service.create(data)


@router.get("", response_model=list[Transaction], status_code=200)
def list_transactions() -> list[Transaction]:
    return service.list_all()


@router.get("/{transaction_id}", response_model=Transaction, status_code=200)
def get_transaction(transaction_id: UUID) -> Transaction:
    transaction = service.get_by_id(transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction
