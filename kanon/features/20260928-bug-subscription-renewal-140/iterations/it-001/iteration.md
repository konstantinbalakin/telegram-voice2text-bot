---
status: open
source: operator
scenario: полигон шаг 1 — первая покупка Pro (месяц), карта/YooKassa
---

# it-001: перепутаны цены rub/stars в _do_buy_subscription

## Что нашли

Шаг 1 полигона: покупка Pro (месяц) по карте → «Ошибка создания платежа:
Сумма 0.9 ₽ ниже минимальной». В БД месяц Pro = 18000 коп (180₽) / 90 stars.

## Что решили

Субагент волны 5 при добавлении ветки YooKassa перепутал распаковку кортежа
`(amount_rub, amount_stars)`: рублёвый путь получал amount_stars (90 → 0.9₽),
звёздный — amount_rub. В main был только Stars-путь, распаковка была верная —
регрессия волны 5.

## Что поправили

- `src/bot/payment_callbacks.py::_do_buy_subscription`: stars → amount_stars,
  yookassa → amount_rub (копейки)
- Регресс-тест: stars-запрос несёт XTR-цену, рублёвый — копейки
