import logging
import os
import re
import telebot
from telebot import TeleBot
from telebot.types import Update, WebAppInfo, Message
from telebot.util import quick_markup

# --- ENV ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
PAYMENT_PROVIDER_TOKEN = os.getenv('PAYMENT_PROVIDER_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # если используешь вебхуки
WEBHOOK_PATH = '/bot'
APP_URL = os.getenv('APP_URL')          # фронт (Vercel)
ORDER_CHANNEL_ID = int(os.getenv('ORDER_CHANNEL_ID', '0'))                 # -100... если шлём в канал
ADMIN_CHAT_IDS = [int(x) for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x]  # 111,222,...

# --- BOT ---
bot: TeleBot = TeleBot(BOT_TOKEN)

# --- STORE (берём сохранённый заказ по payload) ---
# см. app/orders_store.py — там put()/get()/pop()
try:
    from .orders_store import get as store_get, pop as store_pop
except Exception:
    # на всякий случай, если импорт relative не сработает
    from app.orders_store import get as store_get, pop as store_pop  # type: ignore

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
            print(f'notify_admins(user {uid}) error:', e)

# --- HELPERS ---

def _fmt_addr(addr) -> str:
    if not addr:
        return ''
    parts = [
        getattr(addr, 'country_code', None),
        getattr(addr, 'state', None),
        getattr(addr, 'city', None),
        getattr(addr, 'street_line1', None),
        getattr(addr, 'street_line2', None),
        getattr(addr, 'post_code', None),
    ]
    return ', '.join([p for p in parts if p])

def _fmt_items(items) -> str:
    """
    items: список словарей вида:
      { "name": "...", "variant": "M", "qty": 2, "price": 2500 }
    """
    lines = []
    total = 0
    for it in items or []:
        qty = int(it.get('qty', 1))
        price = int(it.get('price', 0))
        line_total = qty * price
        total += line_total
        var = it.get('variant')
        var_txt = f" — {var}" if var else ""
        lines.append(f"• {it.get('name','?')}{var_txt} ×{qty} — {line_total:,} ₽".replace(",", " "))
    if not lines:
        return "_(no items stored)_"
    return "\n".join(lines)

# --- HANDLERS ---

@bot.pre_checkout_query_handler(func=lambda _: True)
def handle_pre_checkout_query(pre_checkout_query):
    """Одобряем чекаут (в демо не отклоняем товары)."""
    bot.answer_pre_checkout_query(pre_checkout_query_id=pre_checkout_query.id, ok=True)

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
    payload = sp.invoice_payload  # это наш order_id из main.py
    order_data = store_pop(payload) or store_get(payload)  # достаём сохранённый заказ (и очищаем)

    # Сводка по товарам из хранилища
    items_block = _fmt_items(order_data.get('items') if isinstance(order_data, dict) else None)

    # Покупатель
    who = f"@{message.from_user.username}" if message.from_user.username else f"id:{message.from_user.id}"
    name = ''
    phone = ''
    addr_txt = ''
    try:
        if sp.order_info:
            name = getattr(sp.order_info, 'name', '') or ''
            phone = getattr(sp.order_info, 'phone_number', '') or ''
            addr_txt = _fmt_addr(getattr(sp.order_info, 'shipping_address', None))
    except Exception:
        pass

    total_rub = sp.total_amount // 100  # копейки -> ₽

    admin_text = (
        "✅ *Новый оплаченный заказ*\n"
        f"*Сумма:* {total_rub:,} ₽\n".replace(",", " ") +
        f"*Покупатель:* {who} {name}\n" +
        (f"*Телефон:* {phone}\n" if phone else "") +
        (f"*Адрес:* {addr_txt}\n" if addr_txt else "") +
        (f"*Комментарий:* {order_data.get('comment')}\n" if isinstance(order_data, dict) and order_data.get('comment') else "") +
        "\n*Товары:*\n" + items_block + "\n\n" +
        f"`payload:` `{payload}`\n"
        f"`charge:` `{sp.provider_payment_charge_id}`"
    )
    notify_admins(admin_text)

    # ---- Ответ покупателю (как в шаблоне)
    user_name = name or (message.from_user.first_name or 'customer')
    text = (
        f"Thank you for your order, *{user_name}*! "
        "This is not a real cafe, so your card was not charged.\n\nHave a nice day 🙂"
    )
    bot.send_message(chat_id=message.chat.id, text=text, parse_mode='markdown')

@bot.message_handler()
def handle_all_messages(message: Message):
    """Фолбэк для любых других сообщений."""
    send_actionable_message(
        chat_id=message.chat.id,
        text='I can open the shop for you. Tap the button below.'
    )

def send_actionable_message(chat_id: int, text: str):
    """Сообщение с одной WebApp-кнопкой, открывающей Mini App."""
    markup = quick_markup({
        'Explore Menu': {'web_app': WebAppInfo(APP_URL)},
    }, row_width=1)
    bot.send_message(chat_id=chat_id, text=text, parse_mode='markdown', reply_markup=markup)

def refresh_webhook():
    """Снять и поставить вебхук (если используешь вебхуки)."""
    bot.remove_webhook()
    if WEBHOOK_URL:
        bot.set_webhook(
            url=WEBHOOK_URL + WEBHOOK_PATH,
            allowed_updates=['message', 'callback_query', 'pre_checkout_query']
        )
    return True

def process_update(update_json: dict):
    """Пробросить входящий Update в бота (используется вебсервером)."""
    update = Update.de_json(update_json)
    bot.process_new_updates([update])

def create_invoice_link(prices, *, payload: str, title='Order', description=''):
    """Создать ссылку на оплату в RUB с вашим payload (order_id)."""
    return bot.create_invoice_link(
        title=title,
        description=description or 'Оплата заказа',
        payload=payload,                        # ВАЖНО: сюда кладём order_id
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency='RUB',
        prices=prices,
        need_name=True,
        need_phone_number=True,
        need_shipping_address=True
    )

def enable_debug_logging():
    telebot.logger.setLevel(logging.DEBUG)