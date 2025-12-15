# backend/app/main.py
import json
import os
from . import auth, bot
from dotenv import load_dotenv
from flask import Flask, request
from flask_cors import CORS
from telebot.types import LabeledPrice
import uuid, time
from typing import Any, Dict

ORDERS_FILE = 'data/orders.json'

# Load environment variables
load_dotenv()

# цены в минимальных единицах (рубли -> копейки = 100)
PRICE_MULTIPLIER = int(os.getenv("PRICE_MULTIPLIER", "100"))

app = Flask(__name__)
app.url_map.strict_slashes = False

allowed_origins = [os.getenv('APP_URL')]
if os.getenv('DEV_MODE') is not None:
    allowed_origins.append(os.getenv('DEV_APP_URL'))
    bot.enable_debug_logging()

CORS(app, origins=list(filter(lambda o: o is not None, allowed_origins)))

# ---------- storage helpers ----------
def _ensure_orders_file():
    data_dir = os.path.dirname(ORDERS_FILE)
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    if not os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)

def _load_orders() -> Dict[str, Any]:
    _ensure_orders_file()
    try:
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def _save_orders(orders: Dict[str, Any]) -> None:
    _ensure_orders_file()
    with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

def _save_order(order_id: str, payload: Dict[str, Any]) -> None:
    orders = _load_orders()
    orders[order_id] = payload
    _save_orders(orders)

# ---------- routes ----------
@app.route(bot.WEBHOOK_PATH, methods=['POST'])
def bot_webhook():
    bot.process_update(request.get_json())
    return { 'message': 'OK' }

@app.route('/info')
def info():
    try:
        return json_data('data/info.json')
    except FileNotFoundError:
        return { 'message': 'Could not find cafe information.' }, 404

@app.route('/categories')
def categories():
    try:
        return json_data('data/categories.json')
    except FileNotFoundError:
        return { 'message': 'Could not find categories list.' }, 404

@app.route('/menu/<category_id>')
def category_menu(category_id: str):
    try:
        return json_data(f'data/menu/{category_id}.json')
    except FileNotFoundError:
        return { 'message': f'Could not find `{category_id}` category data.' }, 404

@app.route('/menu/details/<menu_item_id>')
def menu_item_details(menu_item_id: str):
    try:
        for category_id in ['popular', 'burgers', 'pizza', 'pasta', 'coffee', 'ice-cream']:
            menu_items = json_data(f'data/menu/{category_id}.json')
            for menu_item in menu_items:
                if menu_item['id'] == menu_item_id:
                    return menu_item
        raise FileNotFoundError()
    except FileNotFoundError:
        return { 'message': f'Could not find `{menu_item_id}` menu item.' }, 404

@app.route('/order', methods=['POST'])
def create_order():
    """
    Принимает {_auth, cartItems, form?, currency?}, валидирует, сохраняет заказ
    и возвращает ссылку на оплату (invoiceUrl). Поля для ввода ИМЯ/ТЕЛЕФОН/АДРЕС
    теперь показываются в Telegram-окне оплаты (need_* = True).
    """
    request_data = request.get_json()

    auth_data = request_data.get('_auth')
    if auth_data is None or not auth.validate_auth_data(bot.BOT_TOKEN, auth_data):
        return { 'message': 'Request data should contain valid auth data.' }, 401

    order_items = request_data.get('cartItems')
    if order_items is None:
        return { 'message': 'Cart Items are not provided.' }, 400

    form = request_data.get('form', {})      # из MiniApp (если отправляешь)
    currency = request_data.get('currency', 'RUB')

    # Собираем позиции для Telegram и компактную корзину для сохранения
    labeled_prices = []
    compact_cart = []
    for order_item in order_items:
        name = order_item['cafeItem']['name']
        variant = order_item['variant']['name']
        cost = int(order_item['variant']['cost'])
        quantity = int(order_item['quantity'])

        price_minor = cost * PRICE_MULTIPLIER
        amount = price_minor * quantity

        labeled_prices.append(LabeledPrice(
            label=f"{name} ({variant}) x{quantity}",
            amount=amount
        ))

        compact_cart.append({
            'name': name,
            'variant': variant,
            'qty': quantity,
            'price_minor': price_minor
        })

    # Генерим order_id и сохраняем корзину + форму (если была)
    order_id = uuid.uuid4().hex[:12]
    _save_order(order_id, {
        'created_at': int(time.time()),
        'cart': compact_cart,
        'form': form,
        'currency': currency
    })

    # ВАЖНО: включаем поля Telegram (имя/телефон/адрес)
    invoice_url = bot.create_invoice_link(
        prices=labeled_prices,
        payload=order_id,
        currency=currency,
        need_name=True,
        need_phone_number=True,
        need_shipping_address=True  # адрес через shipping
    )

    return { 'invoiceUrl': invoice_url, 'orderId': order_id }

def json_data(data_file_path: str):
    if os.path.exists(data_file_path):
        with open(data_file_path, 'r', encoding='utf-8') as data_file:
            return json.load(data_file)
    else:
        raise FileNotFoundError()

# при старте обновляем вебхук
bot.refresh_webhook()