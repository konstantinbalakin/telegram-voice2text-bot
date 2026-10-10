# user_subscriptions: схема статусов (#140)

Каждая покупка — отдельная строка `user_subscriptions` с собственным
жизненным циклом. Статусы: `active` | `queued` | `expired` |
`cancelled` | `replaced`.

Инварианты (partial unique index `ix_user_subscriptions_unique_active`,
миграция e7a1b2c3d4f5, WHERE status='active'):
- `COUNT(status='active') <= 1` на пользователя — обеспечен БД
- `COUNT(status='queued') <= 1` — обеспечен сервисом (purchase_subscription)

Семантика статусов:
- `active` — текущая оплаченная подписка; строка-источник дат.
- `queued` — оплачена при живой active; `started_at` = плановый старт
  (= expires_at текущей на момент покупки, Д1), `expires_at` НЕ
  пересчитывается при активации кроном. Продление и даунгрейд при
  живой active оба дают queued: даунгрейд — queued с оплаченным
  периодом (it-004), `next_subscription_tier_id` больше не используется
  платёжным потоком (колонка остаётся в схеме для совместимости).
- `replaced` — старая строка при апгрейде (Д2: новая active сразу,
  остаток дней переносится; отличать от user-cancelled).
- `cancelled` — юзером (до конца срока действует) ИЛИ отменённая
  queued перед пересозданием (Д3).
- `expired` — строка после истечения периода.

Stale-active (active с прошедшим expires_at) гасится в трёх местах
(it-005): покупка, крон, ленивая активация в get_active_subscription —
UNIQUE-инвариант при ленивой активации больше не приводит к сбоям.

Выдача подписки атомарна: INSERT строки + mark_completed покупки в
одной транзакции.

Новых миграций #140 не требует: partial index уже существует, BACKFILL
не нужен (queued появляются только новыми покупками).

`purchases.status` дополняется `abandoned` (брошенные инвойсы; значения
уже встречались в БД вручную — теперь в enum).
