import { Route } from "../routing/route.js";
import { Cart } from "../cart/cart.js";
import { TelegramSDK } from "../telegram/telegram.js";

export class CheckoutPage extends Route {
    constructor() {
        super('checkout', '/pages/checkout.html');
    }

    load() {
        TelegramSDK.expand();
        $('#checkout-form').on('submit', (e) => {
            e.preventDefault();
            this.#submitOrder();
        });
    }

    #submitOrder() {
        const data = {
            cart: Cart.getItems(),
            name: $('#checkout-name').val(),
            phone: $('#checkout-phone').val(),
            payMethod: $('input[name="pay-method"]:checked').val()
        };
        TelegramSDK.sendData(JSON.stringify(data));
        TelegramSDK.showAlert('Заказ отправлен, мы свяжемся с вами!', () => {
            Cart.clear();
            TelegramSDK.close();
        });
    }
}
