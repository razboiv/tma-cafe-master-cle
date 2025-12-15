import json
import os
import uuid
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from telebot.types import LabeledPrice

# внутренние модули
from . import auth, bot  # bot используется для refresh_webhook() внизу

# create_invoice_link() — создаёт ссылку на оплату в RUB c payload
try:
    from .bot import create_invoice_link
except Exception:
    # на случай особенностей импорта
    from app.bot import create_invoice_link  # type: ignore

# простое in-memory хранилище заказа до оплаты
try:
    from .orders_store import put as save_order
except Exception:
    from app.orders_store import put as save_order  # type: ignore

# ──────────────────────────────────────────────────────────────────────────────
# ENV / CONFIG
# ──────────────────────────────────────────────────────────────────────────────

# Загружаем локальные переменные окружения (в проде обычно не нужно)
load_dotenv()

# Рубли -> копейки (целые минимальные единицы для Telegram)
PRICE_MULTIPLIER = int(os.getenv("PRICE_MULTIPLIER", "100"))

# Базовая директория backend (где лежит папка data/)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")

# ──────────────────────────────────────────────────────────────────────────────
# APP
# ──────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _abs_path(rel_path: str) -> str:
    """
    Возвращает абсолютный путь к файлу данных.
    Поддерживает как 'categories.json', так и 'data/menu/hoodie.json'.
    """
    rel_path = rel_path.lstrip("/")

    # если уже начинается с 'data/', добавим от BASE_DIR
    if rel_path.startswith("data/"):
        return os.path.join(BASE_DIR, rel_path)

    # иначе считаем, что относительно DATA_DIR
    return os.path.join(DATA_DIR, rel_path)


def json_data(rel_path: str):
    """
    Загружает JSON из файла по относительному пути (от папки data/).
    Примеры:
      json_data('data/categories.json')
      json_data('menu/hoodie.json')
    """
    data_file_path = _abs_path(rel_path)
    if not os.path.exists(data_file_path):
        raise FileNotFoundError(data_file_path)
    with open(data_file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _prepare_order_and_prices(items: list, comment: str | None = None):
    """
    items — массив из фронта вида:
      {
        "name": "REVERSIBLE FUR ZIP HOODIE in BLACK",
        "variant": {"id":"m","name":"M","cost":"2500"},
        "quantity": 2
      }
    Возвращает:
      saved_items — для orders_store (для уведомлений),
      prices — список LabeledPrice для Telegram (в копейках),
      total_rub — сумма в рублях (целое).
    """
    saved_items = []
    prices: list[LabeledPrice] = []
    total_rub = 0

    for itm in items or []:
        name = itm.get("name") or "Item"
        variant = (itm.get("variant") or {})
        var_name = variant.get("name")
        rub = int(variant.get("cost", 0))
        qty = int(itm.get("quantity", 1))

        line_total_rub = rub * qty
        total_rub += line_total_rub

        # Сохраняем для последующего уведомления
        saved_items.append({
            "name": name,
            "variant": var_name,
            "qty": qty,
            "price": rub,
        })

        # Готовим позиции для инвойса (в копейках!)
        label = f"{name}"
        if var_name:
            label += f" — {var_name}"
        if qty > 1:
            label += f" ×{qty}"
        prices.append(LabeledPrice(label=label, amount=line_total_rub * PRICE_MULTIPLIER))

    return saved_items, prices, total_rub


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True}


@app.get("/info")
def info():
    """Отдаёт общий инфо-блок: backend/data/info.json"""
    try:
        return json_data("data/info.json")
    except FileNotFoundError:
        return {"message": "Could not find info data."}, 404


@app.get("/categories")
def categories():
    """Отдаёт список категорий: backend/data/categories.json"""
    try:
        return json_data("data/categories.json")
    except FileNotFoundError:
        return {"message": "Could not find categories data."}, 404


@app.get("/menu/<category_id>")
def menu(category_id: str):
    """Товары категории: backend/data/menu/<category_id>.json"""
    try:
        return json_data(f"data/menu/{category_id}.json")
    except FileNotFoundError:
        return {"message": f"Could not find menu data for category: {category_id}."}, 404


@app.post("/invoice")
def create_invoice():
    """
    Создаёт инвойс/ссылку на оплату в рублях.
    Ожидает JSON:
      {
        "items": [ { "name": "...", "variant": {"name":"M","cost":"2500"}, "quantity": 2 }, ... ],
        "comment": "опционально"
      }
    Возвращает:
      { "ok": true, "pay_url": "<telegram invoice url>", "payload": "<order_id>" }
    """
    # (если нужна авторизация — раскомментируй и реализуй в auth)
    # if not auth.is_request_authorized(request):
    #     return {"message": "Unauthorized"}, 401

    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    comment = data.get("comment") or ""

    saved_items, prices, total_rub = _prepare_order_and_prices(items, comment)

    # order_id для payload
    order_id = f"ord_{uuid.uuid4().hex[:12]}"
    save_order(order_id, {
        "items": saved_items,
        "comment": comment,
        "total": total_rub
    })

    # создаём ссылку на оплату с payload=order_id
    try:
        pay_url = create_invoice_link(
            prices,
            payload=order_id,
            title=f"Order {order_id}",
            description="Оплата заказа"
        )
    except Exception as e:
        return {"ok": False, "message": f"Failed to create invoice: {e}"}, 500

    return jsonify({"ok": True, "pay_url": pay_url, "payload": order_id})


# ──────────────────────────────────────────────────────────────────────────────
# Utils
# ──────────────────────────────────────────────────────────────────────────────

def read_json_data(data_file_path: str):
    """
    Оставил для совместимости — если где-то вызывается старая функция.
    """
    return json_data(data_file_path)


# при старте перерегистрируем вебхук (если используется)
bot.refresh_webhook()