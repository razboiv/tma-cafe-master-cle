import logging
import os
import re
import json
import telebot
from telebot import TeleBot
from telebot.types import Update, WebAppInfo, Message
from telebot.util import quick_markup

# --- ENV ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
PAYMENT_PROVIDER_TOKEN = os.getenv('PAYMENT_PROVIDER_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # полный https URL, если используешь вебхуки
WEBHOOK_PATH = '/bot'
APP_URL = os.getenv('APP_URL')          # твой фронт (Vercel) для WebApp-кнопки
ORDER_CHANNEL_ID = int(os.getenv('ORDER_CHANNEL_ID', '0'))                 # -100... если шлём в канал
ADMIN_CHAT_IDS = [int(x) for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x]  # 111,222,...

bot: TeleBot = TeleBot(BOT_TOKEN)

# --- ORDERS STORAGE (shared with Flask app) ---
ORDERS_FILE = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'data', 'orders.json'))

def _load_orders():
    try:
        with open(ORDERS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def _get_order(order_id: str):
    orders = _load_orders()
    return orders.get(order_id)

def _money(minor: int) -> str:
    return f"{minor/100:.2f}"

def _format_order(order: dict, currency: str) -> str:
    cart = order.get('cart', [])
    form = order.get('form', {})
    lines = []
    lines.append('*Состав заказа:*')
    total = 0
    for it in cart:
        qty = int(it.get('qty', 1))
        price_minor = int(it.get('price_minor', 0))
        line_total = price_minor * qty
        total += line_total
        title = f"{it.get('name','')} ({it.get('variant','')})".strip()
        lines.append(f"• {title} × {qty} — {_money(line_total)} {currency}")
    lines.append('')
    lines.append(f"*Итого:* {_money(total)} {currency}")
    lines.append('')
    lines.append('*Данные покупателя:*')
    lines.append(f"Имя: {form.get('name','—')}")
    lines.append(f"Телефон: {form.get('phone','—')}")
    lines.append(f"Город: {form.get('city','—')}")
    lines.append(f"Адрес: {form.get('address','—')}")
    return "\n".join(lines)

# --- WEBHOOK mgmt ---
def refresh_webhook():
    """Сбросить/установить вебхук (вызывается из Flask main.py)."""
    try:
        bot.delete_webhook()
    except Exception:
        pass
    if WEBHOOK_URL:
        bot.set_webhook(url=f"{WEBHOOK_URL}{WEBHOOK_PATH}", allowed_updates=[
            'message',
            'edited_message',
            'callback_query',
            'pre_checkout_query',
            'shipping_query'
        ])

def process_update(update_json: dict):
    """Прокидываем апдейт из Flask в telebot."""
    update = Update.de_json(update_json)
    bot.process_new_updates([update])

# --- HANDLERS ---
@bot.message_handler(func=lambda message: re.match(r'/?start', message.text or '', re.IGNORECASE) is not None)
def handle_start_command(message: Message):
    """Welcome + кнопка открытия Mini App."""
    send_actionable_message(
        chat_id=message.chat.id,
        text='*Welcome to MAISON NOIR!*\n\nPress the "open" button to start.'
    )

@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message: Message):
    """Вызвается, когда Telegram подтвердил успешную оплату."""
    sp = message.successful_payment
    order_id = getattr(sp, 'invoice_payload', None)

    # Построим текст для админов и пользователя
    currency = getattr(sp, 'currency', 'RUB')
    who = f"@{message.from_user.username}" if message.from_user.username else f"id:{message.from_user.id}"
    name = ''
    try:
        if sp.order_info and getattr(sp.order_info, 'name', None):
            name = sp.order_info.name
    except Exception:
        name = ''

    order_text = ''
    order_data = _get_order(order_id) if order_id else None
    if order_data:
        order_text = _format_order(order_data, currency)
    else:
        order_text = '*Детали заказа не найдены.*'

    admin_text = (
        '✅ *Новый оплаченный заказ*\n'
        f'Сумма: *{sp.total_amount/100:.2f} {currency}*\n'
        f'Покупатель: {who} {name}\n'
        f'Order ID (payload): `{order_id or "—"}`\n'
        f'Charge ID (TG): `{sp.telegram_payment_charge_id}`\n'
        f'Charge ID (Provider): `{sp.provider_payment_charge_id}`\n\n'
        f'{order_text}'
    )
    notify_admins(admin_text)

    # ---- Ответ покупателю
    user_name = order_data.get('form',{}).get('name') if order_data else (name or (message.from_user.first_name or 'customer'))
    user_text = (
        f'Thank you for your order, *{user_name}*!\n\n'
        f'{order_text}\n\n'
        'We will contact you shortly.'
    )
    bot.send_message(chat_id=message.chat.id, text=user_text, parse_mode='Markdown')

@bot.message_handler()
def handle_all_messages(message: Message):
    """Фолбэк для любых других сообщений."""
    send_actionable_message(
        chat_id=message.chat.id,
        text='I can open the shop for you. Tap the button below.'
    )

# --- HELPERS ---
def send_actionable_message(chat_id: int, text: str):
    """Сообщение с одной WebApp-кнопкой, открывающей Mini App."""
    markup = quick_markup({
        'Explore Menu': {'web_app': WebAppInfo(APP_URL)},
    }, row_width=1)
    bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode='Markdown')

def create_invoice_link(prices, payload: str, currency: str = 'RUB',
                        need_name: bool = False, need_phone_number: bool = False, need_shipping_address: bool = False) -> str:
    """Создать ссылку на оплату в выбранной валюте с коротким payload (order_id)."""
    return bot.create_invoice_link(
        title='Order',
        description='Оплата заказа в MAISON NOIR',
        payload=payload,
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
        need_name=need_name,
        need_phone_number=need_phone_number,
        need_shipping_address=need_shipping_address
    )

# --- NOTIFICATIONS ---
def notify_admins(text: str) -> None:
    """Шлём уведомление в канал и/или лички админов."""
    if ORDER_CHANNEL_ID:
        try:
            bot.send_message(ORDER_CHANNEL_ID, text, parse_mode='Markdown')
        except Exception as e:
            print('notify_admins(channel) error:', e)
    for uid in ADMIN_CHAT_IDS:
        try:
            bot.send_message(uid, text, parse_mode='Markdown')
        except Exception as e:
            print(f'notify_admins({uid}) error:', e)

def enable_debug_logging():
    """Включить подробные логи telebot."""
    telebot.logger.setLevel(logging.DEBUG)