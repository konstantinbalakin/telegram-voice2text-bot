# -------------------------------
# Telegram Voice2Text Bot Makefile
# -------------------------------

# Название контейнера/сервиса
SERVICE_NAME := bot
IMAGE_NAME := telegram-voice2text-bot

# Путь к менеджеру зависимостей
UV := uv

# ===== Commands =====

# 🧩 1. Обновить requirements.txt из uv.lock
deps:
	@echo "📦 Экспорт зависимостей через uv..."
	$(UV) export --no-dev --extra faster-whisper --extra openai-api --locked -o requirements.txt
	@echo "✅ requirements.txt обновлён."

# ⚙️ 2. Собрать Docker-образ
build: deps
	@echo "🐳 Собираем Docker-образ..."
	docker compose build --no-cache
	@echo "✅ Образ собран."

# 🚀 3. Запустить контейнер (в фоне)
up:
	@echo "🚀 Запуск контейнера..."
	docker compose up -d
	@docker compose ps

# 🛑 4. Остановить контейнер
down:
	@echo "🛑 Остановка контейнера..."
	docker compose down

# 📜 5. Просмотреть логи
logs:
	docker compose logs -f $(IMAGE_NAME)

# 🔄 6. Полная пересборка (очистка кеша)
rebuild:
	@echo "♻️ Полная пересборка без кеша..."
	docker compose build --no-cache
	docker compose up -d

# 🧹 7. Удалить все неиспользуемые образы и кеш
clean:
	@echo "🧹 Очистка Docker-кеша и старых образов..."
	docker system prune -f
	@echo "✅ Очистка завершена."
