# Инструкции для локального тестирования

## 📋 Предварительные требования

Эти шаги нужно выполнить **ОДИН РАЗ** перед началом тестирования.

### ⚠️ ВАЖНО: Отключите корпоративный VPN перед началом!

Poetry не может обновить зависимости через корпоративный VPN. Отключите VPN для выполнения шагов 1-3.

---

## 🚀 Шаг 1: Обновление зависимостей (ТРЕБУЕТ ОТКЛЮЧЕНИЯ VPN)

```bash
cd /Users/k.balakin/MyProjects/telegram-voice2text-bot

# Обновить poetry.lock с новыми зависимостями
poetry lock

# Установить зависимости с поддержкой faster-whisper
poetry install --extras "faster-whisper"
```

**Что происходит:**
- `poetry lock` - обновляет `poetry.lock` с новыми зависимостями (psutil, опциональные провайдеры)
- `poetry install --extras "faster-whisper"` - устанавливает базовые зависимости + faster-whisper

**Ожидаемый результат:** Все зависимости установлены, включая `psutil` и `faster-whisper`.

---

## 🔧 Шаг 2: Конфигурация .env

Проверьте и обновите файл `.env`:

```bash
# Откройте .env в редакторе
nano .env

# Или используйте IDE
open -a "Visual Studio Code" .env
```

### Минимальная конфигурация для начала:

```bash
# Telegram (обязательно)
TELEGRAM_BOT_TOKEN=your_actual_bot_token

# Провайдеры (для начала используем только faster-whisper)
WHISPER_PROVIDERS=["faster-whisper"]
WHISPER_ROUTING_STRATEGY=single
PRIMARY_PROVIDER=faster-whisper

# FasterWhisper настройки (начните с base)
FASTER_WHISPER_MODEL_SIZE=base
FASTER_WHISPER_DEVICE=cpu
FASTER_WHISPER_COMPUTE_TYPE=int8
FASTER_WHISPER_BEAM_SIZE=5
FASTER_WHISPER_VAD_FILTER=true

# Benchmark mode (пока отключен)
BENCHMARK_MODE=false

# Остальные настройки можно оставить по умолчанию
```

---

## 🧪 Шаг 3: Проверка установки

```bash
# Проверьте, что Poetry environment активен
poetry env info

# Проверьте установленные пакеты
poetry show psutil
poetry show faster-whisper

# Должны увидеть версии:
# psutil: 6.1.x
# faster-whisper: 1.2.x
```

---

## ✅ После выполнения шагов 1-3:

**Можно снова включить корпоративный VPN!**

Все зависимости установлены, дальнейшие шаги не требуют доступа к PyPI.

---

## 🎮 Шаг 4: Запуск бота для тестирования

### Тест 1: Базовая модель FasterWhisper

```bash
# .env должен содержать:
# FASTER_WHISPER_MODEL_SIZE=base
# BENCHMARK_MODE=false

# Запуск бота
poetry run python -m src.main
```

**Действия:**
1. Отправьте боту голосовое сообщение через Telegram
2. Проверьте качество транскрипции
3. Остановите бота (Ctrl+C)

### Тест 2: Модель small (лучшее качество)

```bash
# Обновите .env:
# FASTER_WHISPER_MODEL_SIZE=small

# Перезапустите бота
poetry run python -m src.main
```

**Действия:**
1. Отправьте **то же самое** голосовое сообщение
2. Сравните качество с базовой моделью
3. Оцените скорость обработки

### Тест 3: Модель medium (высокое качество, медленнее)

```bash
# Обновите .env:
# FASTER_WHISPER_MODEL_SIZE=medium

# Перезапустите бота
poetry run python -m src.main
```

### Тест 4: OpenAI API (эталонное качество)

**⚠️ ВНИМАНИЕ: Это API OpenAI, требует API ключ и тратит деньги ($0.006/минуту)!**

```bash
# Установите openai провайдер (если еще не установлен)
poetry install --extras "openai-api"

# Обновите .env:
# WHISPER_PROVIDERS=["openai"]
# PRIMARY_PROVIDER=openai
# OPENAI_API_KEY=sk-your-actual-api-key-here

# Перезапустите бота
poetry run python -m src.main
```

**Действия:**
1. Отправьте **то же самое** голосовое сообщение
2. Это будет эталоном качества для сравнения

---

## 🔬 Шаг 5: BENCHMARK MODE (автоматическое тестирование всех моделей)

**⚠️ ВАЖНО:**
- Это протестирует ВСЕ модели на ОДНОМ голосовом сообщении
- Займет 10-20 минут в зависимости от длительности аудио
- Если включен OpenAI, он также будет протестирован (расходует деньги!)

### Настройка benchmark mode:

```bash
# Обновите .env:
BENCHMARK_MODE=true
WHISPER_PROVIDERS=["faster-whisper", "whisper", "openai"]
WHISPER_ROUTING_STRATEGY=benchmark

# OpenAI опционален - если не хотите тратить деньги, уберите "openai"
# WHISPER_PROVIDERS=["faster-whisper", "whisper"]

# Если тестируете OpenAI, нужен ключ:
OPENAI_API_KEY=sk-your-key-here

# Перезапустите бота
poetry run python -m src.main
```

### Действия в benchmark mode:

1. **Отправьте голосовое сообщение боту** (желательно типичное для ваших задач, 30-60 секунд)

2. **Бот автоматически протестирует:**
   - faster-whisper: tiny, base, small, medium
   - faster-whisper: small (float32, beam10) - варианты для качества
   - whisper: base, small (если установлен)
   - openai: whisper-1 (если настроен и есть ключ)

3. **Получите отчет:**
   - Бот пришлет краткий summary в Telegram
   - Полный markdown отчет сохранится в `./benchmark_reports/benchmark_YYYYMMDD_HHMMSS.md`
   - Бот также отправит файл отчета в Telegram

### Пример отчета:

```markdown
# 🔬 Whisper Models Benchmark Report

## ⚡ Performance Comparison
| Rank | Configuration | Processing Time | RTF | Memory | Quality Score |
|------|--------------|-----------------|-----|--------|---------------|
| 1 | faster-whisper / base / int8 | 28.7s | 0.64x | 450 MB | 92.15% |
| 2 | faster-whisper / small / int8 | 67.2s | 1.49x | 850 MB | 96.78% |
| 3 | faster-whisper / medium / int8 | 245.8s | 5.46x | 1780 MB | 98.91% |

## 💡 Recommendations
- **Fastest:** faster-whisper / base / int8 (28.7s, RTF: 0.64x)
- **Best Quality:** faster-whisper / small / int8 (96.78% similarity to OpenAI)
- **Best Balance:** faster-whisper / small / int8 (96.78% quality, 1.49x RTF)
```

---

## 📊 Шаг 6: Анализ результатов

После всех тестов:

1. **Откройте benchmark отчет** в `./benchmark_reports/`
2. **Сравните:**
   - Processing Time (время обработки)
   - RTF (Realtime Factor): <1.0 = быстрее реального времени
   - Memory (потребление памяти)
   - Quality Score (похожесть на OpenAI API)

3. **Выберите оптимальную модель** на основе баланса качества и скорости

### Ожидаемые результаты на CPU:

| Модель | RTF (CPU) | Память | Качество vs OpenAI | Рекомендация |
|--------|-----------|--------|---------------------|--------------|
| tiny | 0.3x | 380 MB | ~75% | Слишком низкое качество |
| **base** | **0.6x** | **450 MB** | **~90%** | Хорошо для быстрого тестирования |
| **small** | **1.5x** | **850 MB** | **~95%** | **ЛУЧШИЙ БАЛАНС** |
| medium | 5.5x | 1.8 GB | ~98% | Медленно на CPU |
| large-v3 | 15x | 3.5 GB | ~99% | Очень медленно |

**Ожидаемый победитель:** `faster-whisper` с моделью `small` и `int8` compute type.

---

## 🧹 Шаг 7: Финальная настройка (после выбора модели)

После того как выбрали оптимальную модель:

```bash
# Обновите .env с выбранной моделью:
BENCHMARK_MODE=false
WHISPER_PROVIDERS=["faster-whisper"]
WHISPER_ROUTING_STRATEGY=single
PRIMARY_PROVIDER=faster-whisper
FASTER_WHISPER_MODEL_SIZE=small  # Ваш выбор

# Удалите ненужные провайдеры из pyproject.toml (опционально):
# Оставьте только faster-whisper в dependencies
```

---

## ⚠️ Возможные проблемы и решения

### Проблема 1: `poetry lock` падает с ошибкой сети

**Решение:** Отключите корпоративный VPN и повторите.

### Проблема 2: Модель скачивается медленно при первом запуске

**Причина:** Whisper модели довольно большие (base ~140MB, small ~480MB, medium ~1.5GB).

**Решение:** Подождите. Модель скачается один раз и закешируется.

### Проблема 3: Бот не отвечает на голосовые сообщения

**Проверьте:**
- `TELEGRAM_BOT_TOKEN` правильно указан в `.env`
- Бот запущен (`poetry run python -m src.main`)
- В логах нет ошибок

### Проблема 4: Benchmark занимает слишком много времени

**Решение:**
- Отправьте более короткое голосовое сообщение (15-30 секунд)
- Или уберите медленные модели из `benchmark_configs` в `src/config.py`

### Проблема 5: `ImportError: psutil not found`

**Решение:**
```bash
poetry install  # Переустановите зависимости
```

---

## 📝 Логи и отладка

### Просмотр логов:

```bash
# Логи выводятся в консоль при запуске
poetry run python -m src.main

# Уровень детализации можно изменить в .env:
LOG_LEVEL=DEBUG  # Максимальная детализация
LOG_LEVEL=INFO   # Стандартная (рекомендуется)
LOG_LEVEL=WARNING # Минимальная
```

### Файлы для проверки:

- `./benchmark_reports/` - Markdown отчеты benchmark mode
- `./data/bot.db` - SQLite база данных (можно открыть через DB Browser)
- `./logs/` - Логи (если настроено)

---

## ✅ Checklist быстрого старта

- [ ] Отключил корпоративный VPN
- [ ] Выполнил `poetry lock`
- [ ] Выполнил `poetry install --extras "faster-whisper"`
- [ ] Обновил `.env` с `TELEGRAM_BOT_TOKEN`
- [ ] Включил обратно VPN (если нужен)
- [ ] Запустил бота `poetry run python -m src.main`
- [ ] Протестировал с `base` моделью
- [ ] Протестировал с `small` моделью
- [ ] (Опционально) Запустил benchmark mode
- [ ] Выбрал оптимальную модель на основе результатов
- [ ] Обновил `.env` с финальной конфигурацией

---

## 🎯 Ожидаемый результат

После выполнения всех шагов вы будете знать:
- ✅ Какая модель дает лучшее качество на вашем CPU
- ✅ Какая скорость обработки у каждой модели
- ✅ Сколько памяти потребляет каждая модель
- ✅ Какая модель ближе всего к качеству OpenAI API

И сможете выбрать оптимальный вариант для продакшена!

---

**Удачи в тестировании! 🚀**
