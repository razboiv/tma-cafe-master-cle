import { Route } from "../routing/route.js";
import { navigateTo, showSnackbar } from "../routing/router.js";
import { get } from "../requests/requests.js";
import { TelegramSDK } from "../telegram/telegram.js";
import { loadImage, replaceShimmerContent } from "../utils/dom.js";
import { Cart } from "../cart/cart.js";

/**
 * Page for displaying main page content, e.g. cafe info, categories, some menu sections.
 */
export class MainPage extends Route {
    constructor() {
        super('root', '/pages/main.html')
    }

    load(params) {
        this.#updateMainButton();

        this.#loadCafeInfo()
        this.#loadCategories();
        this.#loadPopularMenu();
    }

    #loadCafeInfo() {
        get('/info', (cafeInfo) => {
            this.#fillCafeInfo(cafeInfo);
        });
    }
    
    #loadCategories() {
        get('/categories', (categories) => {
            this.#fillCategories(categories);
        })
    }
    
    #loadPopularMenu() {
        get('/menu/popular', (popularMenu) => {
            this.#fillPopularMenu(popularMenu);
        });
    }
    
    #fillCafeInfo(cafeInfo) {
        loadImage($('#cafe-logo'), cafeInfo.logoImage);
        loadImage($('#cafe-cover'), cafeInfo.coverImage);

        const cafeInfoTemplate = $('#cafe-info-template').html();
        const filledCafeInfoTemplate = $(cafeInfoTemplate);
        filledCafeInfoTemplate.find('#cafe-name').text(cafeInfo.name);
        filledCafeInfoTemplate.find('#cafe-kitchen-categories').text(cafeInfo.kitchenCategories);
        filledCafeInfoTemplate.find('#cafe-rating').text(cafeInfo.rating);
        filledCafeInfoTemplate.find('#cafe-cooking-time').text(cafeInfo.cookingTime);
        filledCafeInfoTemplate.find('#cafe-status').text(cafeInfo.status);
        $('#cafe-info').empty();
        $('#cafe-info').append(filledCafeInfoTemplate);
    }
    
    #fillCategories(categories) {
        $('#cafe-section-categories-title').removeClass('shimmer');
        replaceShimmerContent(
            '#cafe-categories',
            '#cafe-category-template',
            '#cafe-category-icon',
            categories,
            (template, cafeCategory) => {
                template.attr('id', cafeCategory.id);
                template.css('background-color', cafeCategory.backgroundColor);
                template.find('#cafe-category-icon').attr('src', cafeCategory.icon);
                template.find('#cafe-category-name').text(cafeCategory.name);
                template.on('click', () => {
                    const params = JSON.stringify({'id': cafeCategory.id});
                    navigateTo('category', params);
                });
            }
        )
    }
    
    #fillPopularMenu(popularMenu) {
        $('#cafe-section-popular-title').removeClass('shimmer');
        replaceShimmerContent(
            '#cafe-section-popular',
            '#cafe-item-template',
            '#cafe-item-image',
            popularMenu,
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