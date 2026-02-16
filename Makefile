# -------------------------------
# Telegram Voice2Text Bot Makefile
# -------------------------------

# Название контейнера/сервиса
SERVICE_NAME := bot
IMAGE_NAME := telegram-voice2text-bot

# Путь к менеджеру зависимостей
UV := uv

# Корпоративный CA-сертификат для сборки за SSL-прокси (опционально)
ifneq (,$(wildcard .env))
  CORP_CA_CERT_PATH ?= $(shell grep '^CORP_CA_CERT_PATH=' .env 2>/dev/null | head -1 | cut -d= -f2-)
endif

# ===== Commands =====

# 🧩 1. Обновить requirements.txt из uv.lock
deps:
	@echo "📦 Экспорт зависимостей через uv..."
	$(UV) export --no-hashes --no-editable --no-dev --extra faster-whisper --extra openai-api --locked -o requirements.txt
	@grep -v '^\.$$' requirements.txt > requirements.txt.tmp && mv requirements.txt.tmp requirements.txt
	@echo "✅ requirements.txt обновлён."

# ⚙️ 2. Собрать Docker-образ
build: deps
	@echo "🐳 Собираем Docker-образ..."
	@cert_path="$(CORP_CA_CERT_PATH)"; \
	if [ -n "$$cert_path" ]; then cert_path=$$(eval echo "$$cert_path"); fi; \
	if [ -n "$$cert_path" ] && [ -f "$$cert_path" ]; then \
		echo "🔐 Копируем корпоративный CA-сертификат для сборки..."; \
		cp "$$cert_path" .corp-ca-cert.pem; \
	else \
		touch .corp-ca-cert.pem; \
	fi
	@docker compose build --no-cache; ret=$$?; rm -f .corp-ca-cert.pem; exit $$ret
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
	@cert_path="$(CORP_CA_CERT_PATH)"; \
	if [ -n "$$cert_path" ]; then cert_path=$$(eval echo "$$cert_path"); fi; \
	if [ -n "$$cert_path" ] && [ -f "$$cert_path" ]; then \
		cp "$$cert_path" .corp-ca-cert.pem; \
	else \
		touch .corp-ca-cert.pem; \
	fi
	@docker compose build --no-cache; ret=$$?; rm -f .corp-ca-cert.pem; \
	if [ $$ret -ne 0 ]; then exit $$ret; fi
	docker compose up -d

# 🧹 7. Удалить все неиспользуемые образы и кеш
clean:
	@echo "🧹 Очистка Docker-кеша и старых образов..."
	docker system prune -f
	@echo "✅ Очистка завершена."
