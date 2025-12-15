/**
 * Преобразует цену к виду для показа пользователю.
 * Для MAISON NOIR используем рубли без копеек (например: 2 500 ₽).
 * Ожидаем, что в JSON цена хранится в РУБЛЯХ (целое число).
 */
export function toDisplayCost(costInRubles) {
  const n = Number(costInRubles);
  return `${n.toLocaleString('ru-RU')} ₽`;
}