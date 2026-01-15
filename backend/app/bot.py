# backend/app/bot.py
import logging
import os
import re
import json
import telebot
from telebot import TeleBot
from telebot.types import (
    Update,
    WebAppInfo,
    Message,
    LabeledPrice,
    ShippingOption
)

# ========= ENV =========
BOT_TOKEN = os.getenv('BOT_TOKEN')
PAYMENT_PROVIDER_TOKEN = os.getenv('PAYMENT_PROVIDER_TOKEN')

WEBHOOK_URL = os.getenv('WEBHOOK_URL')   # https://... без трейлинга
WEBHOOK_PATH = '/bot'
APP_URL = os.getenv('APP_URL')

ORDER_CHANNEL_ID = int(os.getenv('ORDER_CHANNEL_ID', '0'))
ADMIN_CHAT_IDS = [int(x) for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x]

# ========= BOT =========
bot: TeleBot = TeleBot(BOT_TOKEN, parse_mode='Markdown')

# ========= ORDERS STORAGE =========
ORDERS_FILE = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'data', 'orders.json'))

def _load_orders():
    try:
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def _get_order(order_id: str):
    orders = _load_orders()
    return orders.get(order_id)

def _money(minor: int) -> str:
    return f"{minor/100:.2f}"

def _format_shipping_address(addr) -> str:
    if not addr:
        return "—"
    parts = [
        getattr(addr, 'country_code', None),
        getattr(addr, 'state', None),
        getattr(addr, 'city', None),
        getattr(addr, 'street_line1', None),
        getattr(addr, 'street_line2', None),
        getattr(addr, 'post_code', None),
    ]
    return ", ".join([p for p in parts if p])

def _format_order_cart(order: dict, currency: str) -> str:
    """Только состав заказа и итог — без повторных персональных данных."""
    cart = order.get('cart', [])
    lines = ['*Состав заказа:*']
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
    return "\n".join(lines)

# ========= WEBHOOK MGMT =========
def refresh_webhook():
    try:
        bot.delete_webhook()
    except Exception:
        pass
    if WEBHOOK_URL:
        bot.set_webhook(
            url=f"{WEBHOOK_URL}{WEBHOOK_PATH}",
            allowed_updates=[
                'message',
                'edited_message',
                'callback_query',
                'shipping_query',
                'pre_checkout_query'
            ]
        )

def process_update(update_json: dict):
    update = Update.de_json(update_json)
    bot.process_new_updates([update])

# ========= HANDLERS =========
@bot.message_handler(func=lambda m: re.match(r'/?start', m.text or '', re.IGNORECASE) is not None)
def handle_start(message: Message):
    markup = telebot.util.quick_markup({
        'Open shop': {'web_app': WebAppInfo(APP_URL)}
    }, row_width=1)
    bot.send_message(message.chat.id,
                     '*Welcome to La Fleur!✨*\n\nPress the button to open the shop.',
                     reply_markup=markup)

# --- Нужны при need_shipping_address=True ---
@bot.shipping_query_handler(func=lambda q: True)
def on_shipping_query(q):
    try:
        option = ShippingOption(id='flat', title='Доставка').add_price(LabeledPrice('Доставка', 0))
        bot.answer_shipping_query(q.id, ok=True, shipping_options=[option])
    except Exception as e:
        bot.answer_shipping_query(q.id, ok=False, error_message='Не удалось рассчитать доставку, попробуйте позже.')
        print('shipping_query error:', e)

@bot.pre_checkout_query_handler(func=lambda q: True)
def on_pre_checkout(q):
    try:
        bot.answer_pre_checkout_query(q.id, ok=True)
    except Exception as e:
        bot.answer_pre_checkout_query(q.id, ok=False, error_message='Ошибка подтверждения платежа.')
        print('pre_checkout error:', e)

@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message: Message):
    sp = message.successful_payment
    currency = getattr(sp, 'currency', 'RUB')
    order_id = getattr(sp, 'invoice_payload', None)

    who = f"@{message.from_user.username}" if message.from_user.username else f"id:{message.from_user.id}"

    # Данные, собранные Telegram
    tg_name = ''
    tg_phone = ''
    tg_address = ''
    try:
        if sp.order_info:
            tg_name = getattr(sp.order_info, 'name', '') or ''
            tg_phone = getattr(sp.order_info, 'phone_number', '') or ''
            tg_address = _format_shipping_address(getattr(sp.order_info, 'shipping_address', None))
    except Exception:
        pass

    # Наш сохранённый заказ (для состава корзины)
    saved_order = _get_order(order_id) if order_id else None
    order_text_block = _format_order_cart(saved_order, currency) if saved_order else '*Состав заказа недоступен.*'

    # ---- Админам / в канал
    admin_lines = [
        '✅ *Новый оплаченный заказ*',
        f'Сумма: *{sp.total_amount/100:.2f} {currency}*',
        f'Покупатель: {who}',
        f'Имя (TG): {tg_name or "—"}',
        f'Телефон (TG): {tg_phone or "—"}',
        f'Адрес (TG): {tg_address or "—"}',
        f'Order ID (payload): `{order_id or "—"}`',
        f'Charge ID (TG): `{sp.telegram_payment_charge_id}`',
        f'Charge ID (Provider): `{sp.provider_payment_charge_id}`',
        '',
        order_text_block
    ]
    notify_admins("\n".join(admin_lines))

    # ---- Пользователю: только спасибо + состав + финальная фраза
    customer_name = (saved_order or {}).get('form', {}).get('name') or tg_name or (message.from_user.first_name or 'покупатель')
    user_text = (
        f'Спасибо за ваш заказ, *{customer_name}*.🙏🏻\n\n'
        f'{order_text_block}\n\n'
        'Мы свяжемся с вами в ближайшее время. 🌷'
    )
    bot.send_message(chat_id=message.chat.id, text=user_text)

@bot.message_handler()
def handle_fallback(message: Message):
    markup = telebot.util.quick_markup({
        'Open shop': {'web_app': WebAppInfo(APP_URL)}
    }, row_width=1)
    bot.send_message(message.chat.id, 'Tap the button below to open the shop.', reply_markup=markup)

# ========= INVOICE LINK =========
def create_invoice_link(
    prices,
    payload: str,
    currency: str = 'RUB',
    need_name: bool = True,
    need_phone_number: bool = True,
    need_shipping_address: bool = True
) -> str:
    return bot.create_invoice_link(
        title='Order',
        description='Оплата заказа в La Fleur',
        payload=payload,
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
        need_name=need_name,
        need_phone_number=need_phone_number,
        need_shipping_address=need_shipping_address,
        is_flexible=True if need_shipping_address else False
    )

# ========= NOTIFICATIONS =========
def notify_admins(text: str) -> None:
    if ORDER_CHANNEL_ID:
        try:
            bot.send_message(ORDER_CHANNEL_ID, text)
        except Exception as e:
            print('notify_admins(channel) error:', e)
    for uid in ADMIN_CHAT_IDS:
        try:
            bot.send_message(uid, text)
        except Exception as e:
            print(f'notify_admins({uid}) error:', e)

def enable_debug_logging():
    telebot.logger.setLevel(logging.DEBUG)