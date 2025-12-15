# backend/app/orders_store.py
from typing import Any, Dict, Optional

_ORDERS: Dict[str, Dict[str, Any]] = {}

def put(order_id: str, data: Dict[str, Any]) -> None:
    _ORDERS[order_id] = data

def get(order_id: str) -> Optional[Dict[str, Any]]:
    return _ORDERS.get(order_id)

def pop(order_id: str) -> Optional[Dict[str, Any]]:
    return _ORDERS.pop(order_id, None)