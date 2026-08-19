from fastapi import APIRouter

from app.alpaca.rest_client import get_account_info

router = APIRouter()


@router.get("")
def account():
    """Return current Alpaca paper account snapshot (equity, buying power, P&L)."""
    return get_account_info()
