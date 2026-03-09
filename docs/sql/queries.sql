-- ============================================================================
-- Voice2Text Bot — Полезные SQL-запросы для DBeaver
-- ============================================================================


-- ############################################################################
-- ЧАСТЬ 1: ОБЗОР ВСЕХ ТАБЛИЦ (SELECT * с лимитом)
-- ############################################################################

-- 1. Пользователи бота
SELECT * FROM users ORDER BY created_at DESC LIMIT 100;

-- 2. Записи использования (каждая транскрипция)
SELECT * FROM usage ORDER BY created_at DESC LIMIT 100;

-- 3. Состояния UI транскрипций (какая кнопка активна у сообщения)
SELECT * FROM transcription_states ORDER BY created_at DESC LIMIT 100;

-- 4. Кеш вариантов текста (структурирование, "сделать красиво" и т.д.)
SELECT * FROM transcription_variants ORDER BY created_at DESC LIMIT 100;

-- 5. Сегменты с таймкодами (faster-whisper)
SELECT * FROM transcription_segments ORDER BY created_at DESC LIMIT 100;

-- 6. Биллинг: общие и индивидуальные условия (key-value)
SELECT * FROM billing_conditions ORDER BY id;

-- 7. Биллинг: тарифные планы подписок
SELECT * FROM subscription_tiers ORDER BY display_order;

-- 8. Биллинг: цены подписок (по периодам)
SELECT * FROM subscription_prices ORDER BY tier_id, period;

-- 9. Биллинг: активные подписки пользователей
SELECT * FROM user_subscriptions ORDER BY created_at DESC LIMIT 100;

-- 10. Биллинг: каталог пакетов минут
SELECT * FROM minute_packages ORDER BY display_order;

-- 11. Биллинг: балансы минут пользователей (бонусные + пакетные)
SELECT * FROM user_minute_balances ORDER BY created_at DESC LIMIT 100;

-- 12. Биллинг: дневное использование минут
SELECT * FROM daily_usage ORDER BY date DESC, user_id LIMIT 100;

-- 13. Биллинг: история покупок (подписки + пакеты)
SELECT * FROM purchases ORDER BY created_at DESC LIMIT 100;

-- 14. Биллинг: лог списаний минут (детально по источникам)
SELECT * FROM deduction_log ORDER BY created_at DESC LIMIT 100;


-- ############################################################################
-- ЧАСТЬ 2: ПОЛЕЗНЫЕ АНАЛИТИЧЕСКИЕ ЗАПРОСЫ
-- ############################################################################

-- ==========================================================================
-- ПОЛЬЗОВАТЕЛИ
-- ==========================================================================

-- Все пользователи с читаемой информацией
SELECT
    u.id,
    u.telegram_id,
    u.username,
    u.first_name || ' ' || COALESCE(u.last_name, '') AS full_name,
    u.created_at,
    u.updated_at
FROM users u
ORDER BY u.created_at DESC;

-- Топ пользователей по общему использованию
SELECT
    u.telegram_id,
    u.username,
    u.first_name,
    ROUND(SUM(us.voice_duration_seconds) / 60.0, 1) AS total_minutes,
    COUNT(us.id) AS transcription_count,
    u.created_at
FROM users u
LEFT JOIN usage us ON us.user_id = u.id
GROUP BY u.id
ORDER BY total_minutes DESC
LIMIT 20;

-- Статистика по пользователям и LTV (активность, retention)
SELECT
    u.telegram_id,
    u.first_name,
    u.last_name,
    u.username,
    SUM(CASE WHEN us.user_id IS NOT NULL THEN 1 ELSE 0 END) AS msg_count,
    MIN(us.voice_duration_seconds) AS min_dur_sec,
    MAX(us.voice_duration_seconds) AS max_dur_sec,
    -- Время с последнего сообщения
    CASE
        WHEN MAX(us.created_at) IS NOT NULL THEN
            CAST((julianday('now') - julianday(MAX(us.created_at))) AS INTEGER) || 'd ' ||
            CAST(((julianday('now') - julianday(MAX(us.created_at))) * 24 -
                  CAST((julianday('now') - julianday(MAX(us.created_at))) AS INTEGER) * 24) AS INTEGER) || 'h ' ||
            CAST((((julianday('now') - julianday(MAX(us.created_at))) * 24 * 60) -
                  CAST((julianday('now') - julianday(MAX(us.created_at))) * 24 AS INTEGER) * 60) AS INTEGER) || 'm'
        ELSE NULL
    END AS time_since_last_msg,
    -- Дата последнего сообщения (MSK)
    CASE
        WHEN MAX(us.created_at) IS NOT NULL
        THEN strftime('%Y-%m-%d %H:%M:%S', MAX(us.created_at), '+3 hours')
        ELSE NULL
    END AS last_msg_msk,
    -- Дата первого сообщения (MSK)
    CASE
        WHEN MIN(us.created_at) IS NOT NULL
        THEN strftime('%Y-%m-%d %H:%M:%S', MIN(us.created_at), '+3 hours')
        ELSE NULL
    END AS first_msg_msk,
    -- Время с первого сообщения
    CASE
        WHEN MIN(us.created_at) IS NOT NULL THEN
            CAST((julianday('now') - julianday(MIN(us.created_at))) AS INTEGER) || 'd ' ||
            CAST(((julianday('now') - julianday(MIN(us.created_at))) * 24 -
                  CAST((julianday('now') - julianday(MIN(us.created_at))) AS INTEGER) * 24) AS INTEGER) || 'h ' ||
            CAST((((julianday('now') - julianday(MIN(us.created_at))) * 24 * 60) -
                  CAST((julianday('now') - julianday(MIN(us.created_at))) * 24 AS INTEGER) * 60) AS INTEGER) || 'm'
        ELSE NULL
    END AS time_since_first_msg,
    -- Время с момента регистрации
    CAST((julianday('now') - julianday(u.created_at)) AS INTEGER) || 'd ' ||
    CAST(((julianday('now') - julianday(u.created_at)) * 24 -
          CAST((julianday('now') - julianday(u.created_at)) AS INTEGER) * 24) AS INTEGER) || 'h ' ||
    CAST((((julianday('now') - julianday(u.created_at)) * 24 * 60) -
          CAST((julianday('now') - julianday(u.created_at)) * 24 AS INTEGER) * 60) AS INTEGER) || 'm' AS time_since_registration
FROM users u
LEFT JOIN usage us ON u.id = us.user_id
GROUP BY u.id
ORDER BY last_msg_msk DESC;

-- Новые пользователи за последние 7 дней
SELECT
    u.telegram_id,
    u.username,
    u.first_name,
    u.created_at,
    COUNT(us.id) AS transcriptions
FROM users u
LEFT JOIN usage us ON us.user_id = u.id
WHERE u.created_at >= datetime('now', '-7 days')
GROUP BY u.id
ORDER BY u.created_at DESC;


-- ==========================================================================
-- ИСПОЛЬЗОВАНИЕ / ТРАНСКРИПЦИИ
-- ==========================================================================

-- Последние транскрипции с инфо о пользователе
SELECT
    us.id AS usage_id,
    u.username,
    u.first_name,
    us.voice_duration_seconds,
    ROUND(us.voice_duration_seconds / 60.0, 1) AS duration_min,
    us.model_size,
    us.llm_model,
    ROUND(us.processing_time_seconds, 2) AS process_sec,
    us.transcription_length AS text_len,
    us.created_at
FROM usage us
JOIN users u ON u.id = us.user_id
ORDER BY us.created_at DESC
LIMIT 50;

-- Детальный лог транскрипций с RTF-метриками (Real-Time Factor)
SELECT
    u.telegram_id,
    u.first_name,
    u.last_name,
    u.username,
    -- Длительность аудио (человекочитаемый формат)
    CASE
        WHEN us.voice_duration_seconds >= 3600 THEN
            CAST(us.voice_duration_seconds / 3600 AS INTEGER) || 'h ' ||
            printf('%02d', (us.voice_duration_seconds % 3600) / 60) || 'm ' ||
            printf('%02d', us.voice_duration_seconds % 60) || 's'
        WHEN us.voice_duration_seconds >= 60 THEN
            CAST(us.voice_duration_seconds / 60 AS INTEGER) || 'm ' ||
            printf('%02d', us.voice_duration_seconds % 60) || 's'
        ELSE us.voice_duration_seconds || 's'
    END AS voice_duration,
    -- Время Whisper (1-й этап)
    CASE
        WHEN us.processing_time_seconds >= 3600 THEN
            CAST(us.processing_time_seconds / 3600 AS INTEGER) || 'h ' ||
            printf('%02d', (us.processing_time_seconds % 3600) / 60) || 'm ' ||
            printf('%02d', CAST(us.processing_time_seconds % 60 AS INTEGER)) || 's'
        WHEN us.processing_time_seconds >= 60 THEN
            CAST(us.processing_time_seconds / 60 AS INTEGER) || 'm ' ||
            printf('%02d', CAST(us.processing_time_seconds % 60 AS INTEGER)) || 's'
        ELSE CAST(us.processing_time_seconds AS INTEGER) || 's'
    END AS whisper_time,
    us.model_size,
    -- Время LLM (2-й этап)
    CASE
        WHEN us.llm_processing_time_seconds >= 3600 THEN
            CAST(us.llm_processing_time_seconds / 3600 AS INTEGER) || 'h ' ||
            printf('%02d', (us.llm_processing_time_seconds % 3600) / 60) || 'm ' ||
            printf('%02d', CAST(us.llm_processing_time_seconds % 60 AS INTEGER)) || 's'
        WHEN us.llm_processing_time_seconds >= 60 THEN
            CAST(us.llm_processing_time_seconds / 60 AS INTEGER) || 'm ' ||
            printf('%02d', CAST(us.llm_processing_time_seconds % 60 AS INTEGER)) || 's'
        ELSE CAST(us.llm_processing_time_seconds AS INTEGER) || 's'
    END AS llm_time,
    us.llm_model,
    -- RTF: отношение времени обработки к длительности аудио (меньше = быстрее)
    ROUND(us.processing_time_seconds / us.voice_duration_seconds, 2) AS rtf_whisper,
    ROUND(us.llm_processing_time_seconds / us.voice_duration_seconds, 2) AS rtf_llm,
    ROUND((us.processing_time_seconds + us.llm_processing_time_seconds) / us.voice_duration_seconds, 2) AS rtf_total,
    datetime(us.created_at, '+3 hours') AS created_at_msk
FROM users u
LEFT JOIN usage us ON u.id = us.user_id
WHERE us.voice_duration_seconds > 0
ORDER BY us.created_at DESC;

-- Статистика по дням (количество транскрипций и суммарная длительность)
SELECT
    DATE(us.created_at) AS day,
    COUNT(*) AS transcriptions,
    COUNT(DISTINCT us.user_id) AS unique_users,
    ROUND(SUM(us.voice_duration_seconds) / 60.0, 1) AS total_minutes,
    ROUND(AVG(us.voice_duration_seconds) / 60.0, 1) AS avg_duration_min,
    ROUND(AVG(us.processing_time_seconds), 2) AS avg_process_sec
FROM usage us
WHERE us.voice_duration_seconds IS NOT NULL
GROUP BY DATE(us.created_at)
ORDER BY day DESC
LIMIT 30;

-- Статистика по моделям Whisper
SELECT
    us.model_size,
    COUNT(*) AS count,
    ROUND(AVG(us.voice_duration_seconds), 1) AS avg_duration_sec,
    ROUND(AVG(us.processing_time_seconds), 2) AS avg_process_sec,
    ROUND(AVG(us.transcription_length), 0) AS avg_text_len
FROM usage us
WHERE us.model_size IS NOT NULL
GROUP BY us.model_size
ORDER BY count DESC;

-- Использование LLM-моделей (для интерактивных кнопок)
SELECT
    us.llm_model,
    COUNT(*) AS count,
    ROUND(AVG(us.llm_processing_time_seconds), 2) AS avg_llm_sec
FROM usage us
WHERE us.llm_model IS NOT NULL
GROUP BY us.llm_model
ORDER BY count DESC;


-- ==========================================================================
-- ИНТЕРАКТИВНЫЕ КНОПКИ (варианты и состояния)
-- ==========================================================================

-- Популярность режимов (какие кнопки нажимают чаще)
SELECT
    tv.mode,
    tv.length_level,
    tv.emoji_level,
    tv.timestamps_enabled,
    COUNT(*) AS variant_count,
    tv.generated_by,
    tv.llm_model
FROM transcription_variants tv
GROUP BY tv.mode, tv.length_level, tv.emoji_level, tv.timestamps_enabled
ORDER BY variant_count DESC;

-- Текущие активные состояния UI
SELECT
    ts.id,
    ts.usage_id,
    ts.message_id,
    ts.chat_id,
    ts.active_mode,
    ts.length_level,
    ts.emoji_level,
    ts.timestamps_enabled,
    ts.is_file_message,
    ts.updated_at
FROM transcription_states ts
ORDER BY ts.updated_at DESC
LIMIT 30;


-- ==========================================================================
-- БИЛЛИНГ: ПОДПИСКИ
-- ==========================================================================

-- Тарифы с актуальными ценами (каталог, с учётом версионирования)
SELECT
    st.name AS tier,
    st.daily_limit_minutes AS daily_limit_min,
    st.description AS tier_desc,
    sp.period,
    sp.amount_rub AS rub,
    sp.amount_stars AS stars,
    sp.description AS price_desc,
    sp.is_active,
    sp.valid_from,
    sp.valid_to,
    sp.user_id AS individual_for_user
FROM subscription_tiers st
JOIN subscription_prices sp ON sp.tier_id = st.id
WHERE st.is_active = 1
  AND sp.is_active = 1
  AND sp.valid_from <= datetime('now')
  AND (sp.valid_to IS NULL OR sp.valid_to > datetime('now'))
  AND sp.user_id IS NULL
ORDER BY st.display_order, sp.period;

-- Активные подписки пользователей
SELECT
    us2.id AS sub_id,
    u.telegram_id,
    u.username,
    st.name AS tier,
    us2.period,
    us2.status,
    us2.started_at,
    us2.expires_at,
    us2.auto_renew,
    us2.payment_provider,
    CASE
        WHEN us2.expires_at < datetime('now') THEN 'EXPIRED'
        ELSE 'VALID'
    END AS validity
FROM user_subscriptions us2
JOIN users u ON u.id = us2.user_id
JOIN subscription_tiers st ON st.id = us2.tier_id
ORDER BY us2.created_at DESC;


-- Персональные цены подписок (индивидуальные для пользователей)
SELECT
    u.telegram_id,
    u.username,
    st.name AS tier,
    sp.period,
    sp.amount_rub AS rub,
    sp.amount_stars AS stars,
    sp.valid_from,
    sp.valid_to
FROM subscription_prices sp
JOIN subscription_tiers st ON st.id = sp.tier_id
JOIN users u ON u.id = sp.user_id
WHERE sp.user_id IS NOT NULL
  AND sp.is_active = 1
ORDER BY u.telegram_id, st.display_order;

-- Персональные пакеты минут (индивидуальные для пользователей)
SELECT
    u.telegram_id,
    u.username,
    mp.name,
    mp.minutes,
    mp.price_rub AS rub,
    mp.price_stars AS stars,
    mp.valid_from,
    mp.valid_to
FROM minute_packages mp
JOIN users u ON u.id = mp.user_id
WHERE mp.user_id IS NOT NULL
  AND mp.is_active = 1
ORDER BY u.telegram_id, mp.display_order;


-- ==========================================================================
-- БИЛЛИНГ: ПАКЕТЫ МИНУТ
-- ==========================================================================

-- Каталог пакетов (актуальные глобальные)
SELECT
    mp.name,
    mp.minutes,
    mp.price_rub AS rub,
    mp.price_stars AS stars,
    mp.description,
    mp.is_active,
    mp.valid_from,
    mp.valid_to,
    mp.user_id AS individual_for_user
FROM minute_packages mp
WHERE mp.is_active = 1
  AND mp.valid_from <= datetime('now')
  AND (mp.valid_to IS NULL OR mp.valid_to > datetime('now'))
  AND mp.user_id IS NULL
ORDER BY mp.display_order;

-- Балансы минут пользователей
SELECT
    umb.id,
    u.telegram_id,
    u.username,
    umb.balance_type,
    ROUND(umb.minutes_remaining, 1) AS minutes_left,
    umb.expires_at,
    umb.source_description,
    umb.created_at
FROM user_minute_balances umb
JOIN users u ON u.id = umb.user_id
WHERE umb.minutes_remaining > 0
ORDER BY umb.created_at DESC;


-- ==========================================================================
-- БИЛЛИНГ: ПОКУПКИ И ПЛАТЕЖИ
-- ==========================================================================

-- История покупок с именами пользователей
SELECT
    p.id,
    u.telegram_id,
    u.username,
    p.purchase_type,
    p.item_id,
    p.amount,
    p.currency,
    p.payment_provider,
    p.provider_transaction_id,
    p.status,
    p.created_at,
    p.completed_at
FROM purchases p
JOIN users u ON u.id = p.user_id
ORDER BY p.created_at DESC
LIMIT 50;

-- Сводка по покупкам (выручка)
SELECT
    p.purchase_type,
    p.currency,
    p.payment_provider,
    COUNT(*) AS total_purchases,
    SUM(CASE WHEN p.status = 'completed' THEN 1 ELSE 0 END) AS completed,
    SUM(CASE WHEN p.status = 'completed' THEN p.amount ELSE 0 END) AS revenue
FROM purchases p
GROUP BY p.purchase_type, p.currency, p.payment_provider
ORDER BY revenue DESC;


-- ==========================================================================
-- БИЛЛИНГ: ДНЕВНОЕ ИСПОЛЬЗОВАНИЕ
-- ==========================================================================

-- Использование минут по дням (по пользователям)
SELECT
    du.date,
    u.telegram_id,
    u.username,
    ROUND(du.minutes_used, 1) AS total_min,
    ROUND(du.minutes_from_daily, 1) AS from_daily,
    ROUND(du.minutes_from_bonus, 1) AS from_bonus,
    ROUND(du.minutes_from_package, 1) AS from_package
FROM daily_usage du
JOIN users u ON u.id = du.user_id
ORDER BY du.date DESC, du.minutes_used DESC
LIMIT 50;

-- Агрегат по дням (все пользователи)
SELECT
    du.date,
    COUNT(DISTINCT du.user_id) AS active_users,
    ROUND(SUM(du.minutes_used), 1) AS total_min,
    ROUND(SUM(du.minutes_from_daily), 1) AS from_daily,
    ROUND(SUM(du.minutes_from_bonus), 1) AS from_bonus,
    ROUND(SUM(du.minutes_from_package), 1) AS from_package
FROM daily_usage du
GROUP BY du.date
ORDER BY du.date DESC
LIMIT 30;


-- ==========================================================================
-- БИЛЛИНГ: ЛОГ СПИСАНИЙ
-- ==========================================================================

-- Последние списания минут (откуда списано)
SELECT
    dl.id,
    u.telegram_id,
    u.username,
    dl.usage_id,
    dl.source_type,
    dl.source_id,
    ROUND(dl.minutes_deducted, 2) AS minutes,
    dl.created_at
FROM deduction_log dl
JOIN users u ON u.id = dl.user_id
ORDER BY dl.created_at DESC
LIMIT 50;


-- ==========================================================================
-- БИЛЛИНГ: УСЛОВИЯ
-- ==========================================================================

-- Общие условия (без user_id = глобальные)
SELECT
    bc.key,
    bc.value,
    bc.valid_from,
    bc.valid_to
FROM billing_conditions bc
WHERE bc.user_id IS NULL
ORDER BY bc.key;

-- Индивидуальные условия (конкретным пользователям)
SELECT
    bc.key,
    bc.value,
    u.telegram_id,
    u.username,
    bc.valid_from,
    bc.valid_to
FROM billing_conditions bc
JOIN users u ON u.id = bc.user_id
WHERE bc.user_id IS NOT NULL
ORDER BY u.telegram_id, bc.key;


-- ==========================================================================
-- ОБЩАЯ СВОДКА ПО ПРОЕКТУ
-- ==========================================================================

-- Дашборд: ключевые метрики
SELECT
    (SELECT COUNT(*) FROM users) AS total_users,
    (SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-7 days')) AS new_users_7d,
    (SELECT COUNT(*) FROM usage) AS total_transcriptions,
    (SELECT COUNT(*) FROM usage WHERE created_at >= datetime('now', '-24 hours')) AS transcriptions_24h,
    (SELECT ROUND(SUM(voice_duration_seconds) / 3600.0, 1) FROM usage) AS total_hours_transcribed,
    (SELECT COUNT(*) FROM user_subscriptions WHERE status = 'active') AS active_subscriptions,
    (SELECT COUNT(*) FROM purchases WHERE status = 'completed') AS completed_purchases;
