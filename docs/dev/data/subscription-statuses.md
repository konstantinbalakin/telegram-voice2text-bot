# user_subscriptions: схема статусов (#140)

Инварианты (частичный unique index `ix_user_subscriptions_unique_active`,
миграция e7a1b2c3d4f5, WHERE status='active'):
- `COUNT(status='active') <= 1` на пользователя — обеспечен БД
- `COUNT(status='queued') <= 1` — обеспечен сервисом (purchase_subscription)

Статусы строк: `active` | `queued` | `expired` | `cancelled` | `replaced`.

- `queued` — оплачена при живой active; `started_at` = плановый старт
  (= expires_at текущей на момент покупки, Д1), `expires_at` НЕ
  пересчитывается при активации кроном.
- `replaced` — старая строка при апгрейде (Д2: отличать от user-cancelled).
- `cancelled` — юзером (до конца срока действует) ИЛИ отменённая
  queued перед пересозданием (Д3).

Новых миграций #140 не требует: partial index уже существует, BACKFILL
не нужен (queued появляются только новыми покупками).

`purchases.status` дополняется `abandoned` (брошенные инвойсы; значения
уже встречались в БД вручную — теперь в enum).
