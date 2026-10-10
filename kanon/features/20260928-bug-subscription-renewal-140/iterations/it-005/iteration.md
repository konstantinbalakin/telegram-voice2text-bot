---
status: open
source: e2e
scenario: полигон шаг 4 — /balance при stale-active + due-queued
---

# it-005: UNIQUE constraint в ленивой активации очереди

## Что нашли

Шаг 4 полигона: у юзера stale-active (expires прошёл, статус active — крон
не успел) + due-queued. Ленивая активация в get_active_subscription
пыталась UPDATE queued → active при живом stale-active → IntegrityError
на partial unique index → «Произошла ошибка» в /balance.

Покупка (3.5) и крон stale гасят, ленивый путь волны 3 — нет.

## Что решили

Ленивая активация перед UPDATE гасит stale-active строки (expire), затем
активирует очередь. Тот же инвариант, что у purchase и крона.

## Что поправили

- `_activate_due_queue_for_user`: expire stale-active до активации
- Регресс-тест: stale active + due queued → active без ошибки, stale expired
