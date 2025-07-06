import logging
import os
import re
import json
import time
try:
    import telebot
    from telebot import TeleBot
    from telebot.types import Update, WebAppInfo, Message
    from telebot.util import quick_markup
    _TELEBOT_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    telebot = None
    _TELEBOT_AVAILABLE = False

    class TeleBot:
        def __init__(self, *_, **__):
            pass

        def remove_webhook(self, *_, **__):
            pass

        def set_webhook(self, *_, **__):
            pass

        def message_handler(self, *_, **__):
            def decorator(func):
                return func
            return decorator

        def pre_checkout_query_handler(self, *_, **__):
            def decorator(func):
                return func
            return decorator

        def process_new_updates(self, *_):
            pass

        def process_update(self, *_):
            pass

        def send_message(self, *_, **__):
            pass

        def answer_pre_checkout_query(self, *_, **__):
            pass

        def create_invoice_link(self, *_, **__):
            return ""

    class WebAppInfo:
        def __init__(self, *_, **__):
            pass

    class Update:
        @staticmethod
        def de_json(*_, **__):
            return None

    class Message:
        pass

    def quick_markup(*_, **__):
        return None
from .models import db, Order, Product

BOT_TOKEN = os.getenv('BOT_TOKEN')
PAYMENT_PROVIDER_TOKEN = os.getenv('PAYMENT_PROVIDER_TOKEN')
DOMAIN = os.getenv('DOMAIN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL') or (f"https://{DOMAIN}" if DOMAIN else None)
WEBHOOK_PATH = '/bot'
APP_URL = os.getenv('APP_URL') or (f"https://{DOMAIN}" if DOMAIN else None)
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')

# Preload menu item names for quick lookup when new orders arrive.
_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
_MENU_ITEMS = {}
_MENU_DIR = os.path.join(_DATA_DIR, 'menu')
if os.path.isdir(_MENU_DIR):
    for _file in os.listdir(_MENU_DIR):
        if _file.endswith('.json'):
            with open(os.path.join(_MENU_DIR, _file), 'r') as f:
                try:
                    for item in json.load(f):
                        _MENU_ITEMS[item.get('id')] = item.get('name')
                except Exception:
                    pass

# Add products from the database
try:
    for prod in Product.query.all():
        _MENU_ITEMS[f'db-{prod.id}'] = prod.name
except Exception:
    pass

if _TELEBOT_AVAILABLE and BOT_TOKEN:
    bot = TeleBot(BOT_TOKEN, parse_mode=None)
else:
    _TELEBOT_AVAILABLE = False
    class BotStub:
        def __init__(self, *_, **__):
            pass

        def remove_webhook(self, *_, **__):
            pass

        def set_webhook(self, *_, **__):
            pass

        def message_handler(self, *_, **__):
            def decorator(func):
                return func
            return decorator

        def pre_checkout_query_handler(self, *_, **__):
            def decorator(func):
                return func
            return decorator

        def process_new_updates(self, *_):
            pass

        def process_update(self, *_):
            pass

        def send_message(self, *_, **__):
            pass

        def answer_pre_checkout_query(self, *_, **__):
            pass

        def create_invoice_link(self, *_, **__):
            return ""

    bot = BotStub()

@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message):
    """Message handler for messages containing 'successful_payment' field.
      This message is sent when the payment is successful and the payment flow is done.
      It's a good place to send the user a purchased item (if it is an electronic item, such as a key) 
      or to send a message that an item is on its way.

      The message param doesn't contain info about ordered good - they should be stored separately.
      Find more info: https://core.telegram.org/bots/api#successfulpayment.

      Example of Successful Payment message:
        {
            "update_id":12345,
            "message":{
                "message_id":12345,
                "date":1441645532,
                "chat":{
                    "last_name":"Doe",
                    "id":123456789,
                    "first_name":"John",
                    "username":"johndoe",
                    "type": ""
                },
                "successful_payment": {
                    "currency": "USD",
                    "total_amount": 1000,
                    "invoice_payload": "order_id",
                    "telegram_payment_charge_id": "12345",
                    "provider_payment_charge_id": "12345",
                    "order_info": {
                        "name": "John"
                    }
                }
            }
        }
    """
    user_name = message.successful_payment.order_info.name
    text = f'Спасибо за заказ, *{user_name}*! Это не настоящее кафе, поэтому с вашей карты ничего не списано.\n\nХорошего дня 🙂'
    bot.send_message(
        chat_id=message.chat.id,
        text=text,
        parse_mode='markdown'
    )


@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message: Message):
    """Handle data sent from the Mini App checkout form."""
    try:
        data = json.loads(message.web_app_data.data)
    except Exception:
        bot.send_message(
            message.chat.id,
            'Ошибка оформления заказа, пожалуйста, попробуйте еще раз.'
        )
        return
    try:
        name = data.get('name', '')
        phone = data.get('phone', '')
        pay_method = data.get('payMethod', '')
        cart = data.get('cart', [])

        items_lines = []
        for item in cart:
            cafe_item = item.get('cafeItem', {})
            variant = item.get('variant', {})
            quantity = item.get('quantity', 0)
            item_name = cafe_item.get('name') or _MENU_ITEMS.get(cafe_item.get('id'), '')
            variant_name = variant.get('name', '')
            items_lines.append(f'- {item_name} ({variant_name}) — {quantity} шт.')

        items_text = '\n'.join(items_lines) if items_lines else '-'

        admin_text = (
            f"🆕 *Новый заказ!*\n"
            f"• Имя: {name}\n"
            f"• Телефон: {phone}\n"
            f"• Оплата: {pay_method}\n"
            f"• Товары:\n{items_text}"
        )

        try:
            order = Order(
                chat_id=message.chat.id,
                name=name,
                phone=phone,
                pay_method=pay_method,
                cart=json.dumps(cart)
            )
            db.session.add(order)
            db.session.commit()
        except Exception as db_exc:
            print(db_exc)

        if ADMIN_CHAT_ID:
            bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode='Markdown')

        bot.send_message(
            message.chat.id,
            '✅ Ваш заказ отправлен администрации. Мы свяжемся с вами в ближайшее время!'
        )
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, 'Произошла ошибка при обработке заказа.')

@bot.pre_checkout_query_handler(func=lambda _: True)
def handle_pre_checkout_query(pre_checkout_query):
    """Here we may check if ordered items are still available.
      Since this is an example project, all the items are always in stock, so we answer query is OK.
      For other cases, when you perform a check and find out that you can't sell the items,
      you need to answer ok=False.
      Keep in mind: The check operation should not be longer than 10 seconds. If the Telegram API
      doesn't receive answer in 10 seconds, it cancels checkout.
    """
    bot.answer_pre_checkout_query(pre_checkout_query_id=pre_checkout_query.id, ok=True)

@bot.message_handler(func=lambda message: re.match(r'/?start', message.text, re.IGNORECASE) is not None)
def handle_start_command(message):
    """Message handler for start messages, including '/start' command. This is an example how to
      use Regex for handling desired type of message. E.g. this handlers applies '/start', 
      '/START', 'start', 'START', 'sTaRt' and so on.
    """
    send_actionable_message(
        chat_id=message.chat.id,
        text='*Добро пожаловать в Laurel Cafe!* 🌿\n\nСамое время заказать что-нибудь вкусное 😋 Нажмите кнопку ниже, чтобы начать.'
    )


@bot.message_handler(commands=['broadcast'])
def handle_broadcast(message: Message):
    if str(message.chat.id) != str(ADMIN_CHAT_ID):
        return
    msg = bot.send_message(ADMIN_CHAT_ID, 'Введите текст для рассылки:')
    if _TELEBOT_AVAILABLE:
        bot.register_next_step_handler(msg, process_broadcast_message)


def process_broadcast_message(message: Message):
    if str(message.chat.id) != str(ADMIN_CHAT_ID):
        return
    text = (message.text or '').strip()
    if not text:
        bot.send_message(ADMIN_CHAT_ID, 'Текст рассылки не может быть пустым.')
        return
    try:
        chat_ids = [cid for (cid,) in db.session.query(Order.chat_id).distinct().all() if cid]
    except Exception as exc:
        print(exc)
        chat_ids = []
    sent = 0
    for idx, cid in enumerate(chat_ids):
        try:
            bot.send_message(cid, text)
            sent += 1
        except Exception as e:
            print(e)
        if (idx + 1) % 30 == 0:
            time.sleep(1)
    bot.send_message(ADMIN_CHAT_ID, f'Рассылка выполнена. Сообщение отправлено {sent} пользователям.')

@bot.message_handler()
def handle_all_messages(message):
    """Fallback message handler that is invoced if none of above aren't match. This is a good
      practice to handle all the messages instead of ignoring unknown ones. In our case, we let user
      know that we can't handle the message and just advice to explore the menu using inline button.
    """
    send_actionable_message(
        chat_id=message.chat.id,
        text="Честно говоря, я не знаю, что ответить на это сообщение. Но могу предложить познакомиться с нашим меню – уверен, вы найдёте что-нибудь по вкусу! 😉"
    )

def send_actionable_message(chat_id, text):
    """Method allows to send the text to the chat and attach inline button to it.
      Inline button will open our Mini App on click.
    """
    markup = quick_markup({
        'Открыть меню': {
            'web_app': WebAppInfo(APP_URL)
        },
    }, row_width=1)
    bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='markdown',
        reply_markup=markup
    )

def refresh_webhook():
    """Just a wrapper for remove & set webhook ops."""
    if not _TELEBOT_AVAILABLE:
        return
    url = WEBHOOK_URL
    if not url and DOMAIN:
        url = f"https://{DOMAIN}"
    if not url:
        return
    if not url.endswith('/'):
        url += '/'
    bot.remove_webhook()
    bot.set_webhook(url + WEBHOOK_PATH.lstrip('/'))

def process_update(update_json):
    """Pass received Update JSON to the Bot for processing.
      This method should be typically called from the webhook method.
      
    Args:
        update_json: Update object sent from the Telegram API. See https://core.telegram.org/bots/api#update.
    """
    update = Update.de_json(update_json)
    bot.process_new_updates([update])

def create_invoice_link(prices) -> str:
    """Just a handy wrapper for creating an invoice link for payment. Since this is an example project,
      most of the fields are hardcode.
    """
    return bot.create_invoice_link(
        title='Заказ №1',
        description='Отличный выбор! Остался последний шаг, и мы начнём готовить ;)',
        payload='orderID',
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency='USD',
        prices=prices,
        need_name=True,
        need_phone_number=True,
        need_shipping_address=True
    )

def enable_debug_logging():
    """Display all logs from the Bot. May be useful while developing."""
    if telebot is not None:
        telebot.logger.setLevel(logging.DEBUG)
