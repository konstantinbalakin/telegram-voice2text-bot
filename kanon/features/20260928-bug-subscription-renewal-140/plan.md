# План: продление подписки #140

Основа: дизайн tasks/2026-09-23-subscription-rows-140/0.3_design.md (Д1–Д3 подтверждены).
Формат чекбокса = коммит.

## Волна 1: модель

- [x] SubscriptionStatus += QUEUED/CANCELLED/REPLACED, PurchaseStatus += ABANDONED (src/services/payments/base.py)
- [x] Убедиться: partial unique index ix_user_subscriptions_unique_active (WHERE status='active') уже в миграции e7a1b2c3d4f5 — новых миграций нет; зафиксировать в docs/dev/data/
- [x] Прогон тестов

## Волна 2: сценарии покупки (SubscriptionService)

- [x] deactivate_all_active(user_id) в billing_repositories.py — гасит ВСЕ active независимо от expires_at (первопричина бага, 3.5)
- [x] purchase_subscription(user_id, tier_id, period, provider): роутинг сценария по текущей active + display_order тиров (3.1–3.5)
- [x] Продление (3.2): INSERT queued, started_at=cur.expires_at, expires_at=started_at+период
- [x] Апгрейд (3.3): старая → replaced, новая active с now+период+остаток_дней
- [x] Даунгрейд (3.4): next_tier на active; существующая queued → cancelled (Д3)
- [x] Тесты сценариев 3.1–3.5 + инварианты (≤1 active, ≤1 queued)

## Волна 3: очередь

- [x] check_expired_subscriptions: после expire активировать самую раннюю queued (Д1: expires_at не пересчитываем)
- [x] Ленивая страховка в get_active_subscription: queued с started_at<=now без active → активировать
- [x] Тесты крона и ленивой активации

## Волна 4: платёжный поток

- [x] _activate_subscription → purchase_subscription; activate + mark_completed в ОДНОЙ сессии (unit of work, 4а)
- [x] Регресс-тест: find_pending_purchase не матчит abandoned
- [x] Тест идемпотентности по provider_transaction_id

## Волна 5: UX

- [x] Подтверждение перед оплатой при активной подписке: даты новой (продление/апгрейд/даунгрейд — свои тексты) в payment_callbacks
- [x] Unit-тесты текстов/кнопок

## Волна 6: приёмка

- [x] Полный прогон тестов + kanon check
- [ ] Чек-лист chat-bot на полигоне → verify
