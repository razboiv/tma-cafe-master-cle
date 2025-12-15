import json
import os
import uuid
from typing import List, Dict, Any, Tuple

from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from telebot.types import LabeledPrice

# ── внутренние модули
from . import auth, bot  # bot.refresh_webhook() внизу

try:
    from .bot import create_invoice_link
except Exception:
    from app.bot import create_invoice_link  # type: ignore

try:
    from .orders_store import put as save_order
except Exception:
    from app.orders_store import put as save_order  # type: ignore

# ── ENV / CONFIG ──────────────────────────────────────────────────────────────
load_dotenv()
PRICE_MULTIPLIER = int(os.getenv("PRICE_MULTIPLIER", "100"))  # RUB → копейки

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
MENU_DIR = os.path.join(DATA_DIR, "menu")
DETAILS_DIR = os.path.join(DATA_DIR, "details")

app = Flask(__name__)
# Разрешаем CORS для всего (фронт на Vercel)
CORS(app, resources={r"/*": {"origins": "*"}})

# ── helpers ──────────────────────────────────────────────────────────────────
def _abs_path(rel_path: str) -> str:
    rel_path = rel_path.lstrip("/")
    if rel_path.startswith("data/"):
        return os.path.join(BASE_DIR, rel_path)
    return os.path.join(DATA_DIR, rel_path)

def json_data(rel_path: str):
    p = _abs_path(rel_path)
    if not os.path.exists(p):
        raise FileNotFoundError(p)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def _normalize_variants(variants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for v in variants or []:
        vv = dict(v)
        if not vv.get("name"):
            vv["name"] = vv.get("id", "")
        vv.setdefault("id", (vv.get("id") or vv["name"] or "").lower())
        try:
            vv["cost"] = str(int(float(vv.get("cost", 0))))  # → строка целых рублей
        except Exception:
            vv["cost"] = "0"
        vv.setdefault("weight", f"Size {vv.get('name','')}")
        out.append(vv)
    return out

def _normalize_item(item: Dict[str, Any], category_id: str, idx: int) -> Dict[str, Any]:
    it = dict(item)
    it.setdefault("id", it.get("id") or f"{category_id}-{idx}")
    it["variants"] = _normalize_variants(it.get("variants", []))
    return it

def _prepare_order_and_prices(items: list, comment: str | None = None) -> Tuple[List[Dict[str, Any]], List[LabeledPrice], int]:
    saved_items: List[Dict[str, Any]] = []
    prices: List[LabeledPrice] = []
    total_rub = 0
    for itm in items or []:
        name = itm.get("name") or "Item"
        variant = (itm.get("variant") or {})
        var_name = variant.get("name")
        rub = int(variant.get("cost", 0))
        qty = int(itm.get("quantity", 1))
        line_total_rub = rub * qty
        total_rub += line_total_rub
        saved_items.append({"name": name, "variant": var_name, "qty": qty, "price": rub})
        label = name + (f" — {var_name}" if var_name else "") + (f" ×{qty}" if qty > 1 else "")
        prices.append(LabeledPrice(label=label, amount=line_total_rub * PRICE_MULTIPLIER))
    return saved_items, prices, total_rub

def _find_item_in_menus(item_id: str) -> Dict[str, Any] | None:
    if not os.path.isdir(MENU_DIR):
        return None
    for fname in os.listdir(MENU_DIR):
        if not fname.endswith(".json"):
            continue
        category_id = os.path.splitext(fname)[0]
        try:
            items = json_data(f"data/menu/{fname}")
        except Exception:
            continue
        for i, item in enumerate(items, start=1):
            it = _normalize_item(item, category_id, i)
            if str(it.get("id")) == str(item_id):
                return it
    return None

def _handle_invoice_request(data: dict):
    items = data.get("items") or []
    comment = data.get("comment") or ""
    saved_items, prices, total_rub = _prepare_order_and_prices(items, comment)
    order_id = f"ord_{uuid.uuid4().hex[:12]}"
    save_order(order_id, {"items": saved_items, "comment": comment, "total": total_rub})
    pay_url = create_invoice_link(
        prices,
        payload=order_id,
        title=f"Order {order_id}",
        description="Оплата заказа"
    )
    return {"ok": True, "pay_url": pay_url, "payload": order_id}

# ── routes ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/info")
def info():
    try:
        return json_data("data/info.json")
    except FileNotFoundError:
        return {"message": "Could not find info data."}, 404

@app.get("/categories")
def categories():
    try:
        return json_data("data/categories.json")
    except FileNotFoundError:
        return {"message": "Could not find categories data."}, 404

@app.get("/menu/<category_id>")
def menu(category_id: str):
    try:
        items = json_data(f"data/menu/{category_id}.json")
        normalized = [_normalize_item(item, category_id, i) for i, item in enumerate(items, start=1)]
        return jsonify(normalized)
    except FileNotFoundError:
        return {"message": f"Could not find menu data for category: {category_id}."}, 404
    except Exception as e:
        return {"message": f"menu load error: {e}"}, 500

@app.get("/menu/details/<item_id>")
def menu_details(item_id: str):
    try:
        if os.path.isdir(DETAILS_DIR):
            p = os.path.join(DETAILS_DIR, f"{item_id}.json")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    return jsonify(json.load(f))
        found = _find_item_in_menus(item_id)
        if found:
            return jsonify(found)
        return {"message": f"Item not found: {item_id}"}, 404
    except Exception as e:
        return {"message": f"details error: {e}"}, 500

@app.post("/invoice")
def create_invoice():
    # if not auth.is_request_authorized(request):
    #     return {"message": "Unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    try:
        res = _handle_invoice_request(data)
        return jsonify(res)
    except Exception as e:
        return {"ok": False, "message": f"Failed to create invoice: {e}"}, 500

# ⚠️ Алиас под фронт, который шлёт /order (и CORS preflight OPTIONS)
@app.route("/order", methods=["POST", "OPTIONS"])
def create_order():
    if request.method == "OPTIONS":
        # даём ОК на префлайт
        return ("", 204)
    # if not auth.is_request_authorized(request):
    #     return {"message": "Unauthorized"}, 401
    data = request.get_json(silent=True) or {}
    try:
        res = _handle_invoice_request(data)
        return jsonify(res)
    except Exception as e:
        return {"ok": False, "message": f"Failed to create order: {e}"}, 500

# ── совместимость и webhook ──────────────────────────────────────────────────
def read_json_data(path: str):
    return json_data(path)

bot.refresh_webhook()