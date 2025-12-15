import json
import os
from . import auth, bot
from dotenv import load_dotenv
from flask import Flask, request
from flask_cors import CORS
from telebot.types import LabeledPrice
import uuid, time, pathlib
from typing import Any, Dict

ORDERS_FILE = 'data/orders.json'

# Load environment variables from .env files.
# Typicall environment variables are set on the OS level,
# but for development purposes it may be handy to set them
# in the .env file directly.
load_dotenv()

# рубли -> копейки (целые в минимальных единицах)
PRICE_MULTIPLIER = int(os.getenv("PRICE_MULTIPLIER", "100"))

app = Flask(__name__)
# Handle paths like '/info/' and '/info' as the same.
app.url_map.strict_slashes = False

# List of allowed origins. The production 'APP_URL' is added by default,
# the development `DEV_APP_URL` is added if it and `DEV_MODE` variable is present.
allowed_origins = [os.getenv('APP_URL')]

if os.getenv('DEV_MODE') is not None:
    allowed_origins.append(os.getenv('DEV_APP_URL'))
    bot.enable_debug_logging()
        
CORS(app, origins=list(filter(lambda o: o is not None, allowed_origins)))

def _ensure_orders_file():
    # Create data dir or file if missing
    data_dir = os.path.dirname(ORDERS_FILE)
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    if not os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, 'w') as f:
            json.dump({}, f)

def _load_orders() -> Dict[str, Any]:
    _ensure_orders_file()
    try:
        with open(ORDERS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def _save_orders(orders: Dict[str, Any]) -> None:
    _ensure_orders_file()
    with open(ORDERS_FILE, 'w') as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

def _save_order(order_id: str, payload: Dict[str, Any]) -> None:
    orders = _load_orders()
    orders[order_id] = payload
    _save_orders(orders)

@app.route(bot.WEBHOOK_PATH, methods=['POST'])
def bot_webhook():
    """Entry points for Bot update sent via Telegram API.
      You may find more info looking into process_update method.
    """
    bot.process_update(request.get_json())
    return { 'message': 'OK' }
        
@app.route('/info')
def info():
    """API endpoint for providing info about the cafe.
    
    Returns:
      JSON data from data/info.json file or error message with 404 code if not found.
    """
    try:
        return json_data('data/info.json')
    except FileNotFoundError:
        return { 'message': 'Could not find cafe information.' }, 404

@app.route('/categories')
def categories():
    """API endpoint for providing a list of menu categories.

    Returns:
      JSON data from data/categories.json file or error message with 404 code if not found.
    """
    try:
        return json_data('data/categories.json')
    except FileNotFoundError:
        return { 'message': 'Could not find categories list.' }, 404

@app.route('/menu/<category_id>')
def category_menu(category_id: str):
    """API endpoint for providing menu list of specified category.
    
    Args:
      category_id: Looking menu category ID.

    Returns:
      JSON data from one of data/menu/<category_id>.json file or error message with 404 code if not found.
    """
    try:
        return json_data(f'data/menu/{category_id}.json')
    except FileNotFoundError:
        return { 'message': f'Could not find `{category_id}` category data.' }, 404

@app.route('/menu/details/<menu_item_id>')
def menu_item_details(menu_item_id: str):
    """API endpoint for providing info of the specified menu item.
    
    Args:
      menu_item_id: Desired menu item ID.

    Returns:
      JSON data from one of data/menu/*.json files or error message with 404 code if not found.
    """
    try:
        for category_id in [ 'popular', 'burgers', 'pizza', 'pasta', 'coffee', 'ice-cream' ]:
            menu_items = json_data(f'data/menu/{category_id}.json')
            for menu_item in menu_items:
                if menu_item['id'] == menu_item_id:
                    return menu_item
        raise FileNotFoundError()
    except FileNotFoundError:
        return { 'message': f'Could not find `{menu_item_id}` menu item.' }, 404

@app.route('/order', methods=['POST'])
def create_order():
    """API endpoint for creating an order.
    Validates Mini App initData, converts cart to LabeledPrice list,
    saves the order (cart + form) and returns invoiceUrl.
    """
    request_data = request.get_json()

    auth_data = request_data.get('_auth')
    if auth_data is None or not auth.validate_auth_data(bot.BOT_TOKEN, auth_data):
        return { 'message': 'Request data should contain valid auth data.' }, 401

    order_items = request_data.get('cartItems')
    if order_items is None:
        return { 'message': 'Cart Items are not provided.' }, 400

    form = request_data.get('form', {})  # {'name','phone','city','address',...} — приходит из твоей формы MiniApp
    currency = request_data.get('currency', 'RUB')

    # Prepare LabeledPrice list for Telegram and collect compact cart
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

    # Create short order id and save order data (cart + form)
    order_id = uuid.uuid4().hex[:12]
    _save_order(order_id, {
        'created_at': int(time.time()),
        'cart': compact_cart,
        'form': form,
        'currency': currency
    })

    # Create invoice link with payload containing the order_id
    invoice_url = bot.create_invoice_link(
        prices=labeled_prices,
        payload=order_id,
        currency=currency,
        need_name=False,
        need_phone_number=False,
        need_shipping_address=False
    )

    return { 'invoiceUrl': invoice_url, 'orderId': order_id }

def json_data(data_file_path: str):
    """Extracts data from the JSON file.

    Args:
      data_file_path: Path to desired JSON file.

    Returns:
      Data from the desired JSON file (as dict).

    Raises:
      FileNotFoundError if desired file doesn't exist.
    """
    if os.path.exists(data_file_path):
        with open(data_file_path, 'r') as data_file:
            return json.load(data_file)
    else:
        raise FileNotFoundError()
    
bot.refresh_webhook()