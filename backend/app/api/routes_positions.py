from fastapi import APIRouter

from app.alpaca.rest_client import get_all_positions

router = APIRouter()


@router.get("")
def positions():
    """Return all open positions (equity + options legs)."""
    return get_all_positions()
