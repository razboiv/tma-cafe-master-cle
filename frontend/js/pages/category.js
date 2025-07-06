import { Route } from "../routing/route.js";
import { navigateTo, showSnackbar } from "../routing/router.js";
import { get } from "../requests/requests.js";
import { TelegramSDK } from "../telegram/telegram.js";
import { replaceShimmerContent } from "../utils/dom.js";
import { Cart } from "../cart/cart.js";

/**
 * Page for displaying menu list for selected category.
 */
export class CategoryPage extends Route {
    constructor() {
        super('category', '/pages/category.html')
    }

    load(params) {
        TelegramSDK.expand();

        this.#updateMainButton();

        if (params != null) {
            const parsedParams = JSON.parse(params);
            this.#loadMenu(parsedParams.id);
        } else {
            console.log('Params must not be null and must contain category ID.')
        }
    }

    #loadMenu(categoryId) {
        get('/menu/' + categoryId, (cafeItems) => {
            this.#fillMenu(cafeItems);
        });
    }

    #fillMenu(cafeItems) {
        replaceShimmerContent(
            '#cafe-category',
            '#cafe-item-template',
            '#cafe-item-image',
            cafeItems,
            (template, cafeItem) => {
                template.attr('id', cafeItem.name);
                template.find('#cafe-item-image').attr('src', cafeItem.image);
                template.find('#cafe-item-name').text(cafeItem.name);
                template.find('#cafe-item-description').text(cafeItem.description);
                if (cafeItem.variants && cafeItem.variants.length > 0) {
                    const price = cafeItem.variants[0].cost;
                    template.find('#cafe-item-price').text(`${price}₽`);
                }
                template.find('.product-quantity-value')
                    .attr('id', `qty-${cafeItem.id}`)
                    .text('0');
                template.find('.product-quantity-increment')
                    .attr('data-product', cafeItem.id)
                    .clickWithRipple((e) => { e.stopPropagation(); this.#changeQuantity(cafeItem.id, 1); });
                template.find('.product-quantity-decrement')
                    .attr('data-product', cafeItem.id)
                    .clickWithRipple((e) => { e.stopPropagation(); this.#changeQuantity(cafeItem.id, -1); });
                template.find('.add-to-cart-button')
                    .clickWithRipple((e) => {
                        e.stopPropagation();
                        const qty = parseInt($(`#qty-${cafeItem.id}`).text());
                        if (!isNaN(qty) && qty > 0) {
                            Cart.addItem(cafeItem, cafeItem.variants[0], qty);
                            $(`#qty-${cafeItem.id}`).text('0');
                            this.#updateMainButton();
                            showSnackbar('Товар добавлен в корзину', 'success');
                        }
                    });
                template.on('click', () => {
                    const params = JSON.stringify({'id': cafeItem.id});
                    navigateTo('details', params);
                });
            }
        )
    }

    #getDisplayPositionCount(positionCount) {
        return positionCount == 1 ? `${positionCount} ПОЗИЦИЯ` : `${positionCount} ПОЗИЦИИ`;
    }

    #updateMainButton() {
        const portionCount = Cart.getPortionCount();
        if (portionCount > 0) {
            TelegramSDK.showMainButton(
                `МОЯ КОРЗИНА • ${this.#getDisplayPositionCount(portionCount)}`,
                () => navigateTo('cart')
            );
        } else {
            TelegramSDK.hideMainButton();
        }
    }

    #changeQuantity(id, delta) {
        const valueElement = $(`#qty-${id}`);
        let current = parseInt(valueElement.text());
        if (isNaN(current)) current = 0;
        current += delta;
        if (current < 0) current = 0;
        valueElement.text(current).boop();
    }

}