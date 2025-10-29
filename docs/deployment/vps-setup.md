# VPS Setup Guide для Telegram Voice2Text Bot

Пошаговая инструкция по настройке VPS сервера для автоматического деплоя бота.

## Требования

- **VPS сервер**: Ubuntu 22.04/24.04 LTS (или Debian 11/12)
- **RAM**: Минимум 1GB (рекомендуется 2-3GB для stable production)
- **CPU**: 1-2 cores
- **Disk**: 10GB+ (для Docker images + Whisper models)
- **Доступ**: Root или sudo права
- **Сеть**: Публичный IP адрес

## Фаза 1: Первое подключение к VPS (15 минут)

### Шаг 1.1: Получить данные доступа от провайдера

После покупки VPS провайдер отправит:
- **IP адрес**: например, `123.45.67.89`
- **Username**: обычно `root` или `ubuntu`
- **Password**: временный пароль для первого входа

### Шаг 1.2: Первое подключение по паролю

```bash
# На вашем локальном компьютере (Mac/Linux)
ssh root@YOUR_VPS_IP

# Пример:
ssh root@123.45.67.89

# Введите пароль когда попросит
# При первом подключении спросит:
# "Are you sure you want to continue connecting (yes/no)?"
# Ответьте: yes
```

**Если подключение не работает**:
- Проверьте, что IP адрес правильный
- Убедитесь, что провайдер активировал сервер
- Некоторые провайдеры требуют активации через веб-панель

### Шаг 1.3: Обновить систему

```bash
# После успешного подключения к VPS
apt update && apt upgrade -y
```

---

## Фаза 2: Настройка SSH ключей (15 минут)

### Шаг 2.1: Создать SSH ключи для GitHub Actions

**На вашем локальном компьютере** (НЕ на VPS):

```bash
# Создать отдельную пару ключей для CI/CD
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/telegram_bot_deploy

# Нажмите Enter дважды (no passphrase для автоматизации)
```

Это создаст два файла:
- `~/.ssh/telegram_bot_deploy` - **приватный ключ** (для GitHub Secrets)
- `~/.ssh/telegram_bot_deploy.pub` - **публичный ключ** (для VPS)

### Шаг 2.2: Скопировать публичный ключ на VPS

**Вариант A: Автоматически (рекомендуется)**

```bash
# На локальном компьютере
ssh-copy-id -i ~/.ssh/telegram_bot_deploy.pub root@YOUR_VPS_IP

# Введите пароль VPS в последний раз
```

**Вариант B: Вручную**

```bash
# На локальном компьютере - получить содержимое публичного ключа
cat ~/.ssh/telegram_bot_deploy.pub
# Скопируйте весь вывод (начинается с ssh-ed25519...)

# Подключитесь к VPS по паролю
ssh root@YOUR_VPS_IP

# На VPS - добавить ключ в authorized_keys
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "PASTE_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### Шаг 2.3: Проверить SSH доступ без пароля

**На локальном компьютере**:

```bash
# Отключиться от VPS (если подключены)
exit

# Попробовать подключиться с использованием SSH ключа
ssh -i ~/.ssh/telegram_bot_deploy root@YOUR_VPS_IP

# Должно подключиться БЕЗ запроса пароля
# Если работает - отлично! SSH ключи настроены правильно
```

### Шаг 2.4: Сохранить приватный ключ для GitHub Secrets

```bash
# На локальном компьютере - скопировать приватный ключ
cat ~/.ssh/telegram_bot_deploy

# Скопируйте ВСЁ содержимое, включая строки:
# -----BEGIN OPENSSH PRIVATE KEY-----
# ...
# -----END OPENSSH PRIVATE KEY-----
```

**Сохраните этот ключ** - он понадобится для GitHub Secrets на следующем шаге.

---

## Фаза 3: Установка Docker (10 минут)

**На VPS сервере**:

```bash
# 1. Установить Docker через официальный скрипт
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 2. Добавить текущего пользователя в группу docker
sudo usermod -aG docker $USER

# 3. Включить Docker autostart
sudo systemctl enable docker
sudo systemctl start docker

# 4. Важно! Перелогиниться для применения группы docker
exit

# Подключиться снова
ssh -i ~/.ssh/telegram_bot_deploy root@YOUR_VPS_IP

# 5. Проверить что Docker работает без sudo
docker ps
# Должно вывести пустой список контейнеров (без ошибок)

# 6. Установить Docker Compose (уже включен в Docker Engine)
docker compose version
# Должно показать версию: Docker Compose version v2.x.x
```

---

## Фаза 4: Подготовка структуры проекта (5 минут)

**На VPS сервере**:

```bash
# 1. Создать директорию для проекта
sudo mkdir -p /opt/telegram-voice2text-bot
sudo chown $USER:$USER /opt/telegram-voice2text-bot
cd /opt/telegram-voice2text-bot

# 2. Клонировать репозиторий
git clone https://github.com/konstantinbalakin/telegram-voice2text-bot.git .

# Проверка
ls -la
# Должны увидеть: docker-compose.prod.yml, .github/, src/, и т.д.

# 3. Создать директории для persistence
mkdir -p data logs

# 4. Проверить структуру
pwd
# Должно быть: /opt/telegram-voice2text-bot
```

---

## Фаза 5: Настройка GitHub Secrets (10 минут)

### Шаг 5.1: Открыть настройки GitHub Secrets

1. Открыть репозиторий: https://github.com/konstantinbalakin/telegram-voice2text-bot
2. **Settings** → **Secrets and variables** → **Actions**
3. Нажать **"New repository secret"**

### Шаг 5.2: Добавить необходимые секреты

Добавьте следующие секреты **по одному**:

#### 1. `VPS_HOST`
- **Name**: `VPS_HOST`
- **Secret**: IP адрес вашего VPS (например: `123.45.67.89`)

#### 2. `VPS_USER`
- **Name**: `VPS_USER`
- **Secret**: username для SSH (обычно `root` или `ubuntu`)

#### 3. `VPS_SSH_KEY`
- **Name**: `VPS_SSH_KEY`
- **Secret**: Содержимое приватного ключа `~/.ssh/telegram_bot_deploy` (весь текст, включая `-----BEGIN...-----` и `-----END...-----`)

**Примечание**: Остальные секреты (`TELEGRAM_BOT_TOKEN`, `DOCKER_USERNAME`, `DOCKER_PASSWORD`) должны быть уже настроены.

### Шаг 5.3: Проверить список секретов

Должны быть настроены:
- ✅ `TELEGRAM_BOT_TOKEN`
- ✅ `DOCKER_USERNAME`
- ✅ `DOCKER_PASSWORD`
- ✅ `VPS_HOST` ← NEW
- ✅ `VPS_USER` ← NEW
- ✅ `VPS_SSH_KEY` ← NEW

---

## Фаза 6: Первый автоматический деплой (20 минут)

### Шаг 6.1: Создать feature branch для тестирования

**На вашем локальном компьютере** (в директории проекта):

```bash
# Убедиться что на main ветке и она актуальна
git checkout main
git pull origin main

# Создать тестовую ветку
git checkout -b feat/activate-vps-deployment

# Создать минимальное изменение для триггера деплоя
echo "# VPS deployment activated" >> DEPLOYMENT.md

# Закоммитить
git add DEPLOYMENT.md
git commit -m "feat: activate VPS deployment"

# Запушить в GitHub
git push origin feat/activate-vps-deployment
```

### Шаг 6.2: Создать Pull Request

```bash
# Создать PR через gh CLI (или через веб-интерфейс GitHub)
gh pr create \
  --title "feat: activate VPS deployment" \
  --body "🚀 Activating automated VPS deployment

**Changes:**
- Corrected memory requirements (6GB → 2GB actual)
- Created docker-compose.prod.yml
- Updated deploy workflow .env generation (base → medium)
- Added VPS_SETUP.md guide
- Configured GitHub secrets for VPS

**Testing:**
- [ ] CI pipeline passes
- [ ] Docker build succeeds
- [ ] Deployment to VPS successful
- [ ] Bot responds in Telegram"
```

### Шаг 6.3: Дождаться прохождения CI

1. Открыть PR в GitHub
2. Проверить что **CI workflow** запустился
3. Дождаться зеленой галочки ✅ (тесты, mypy, ruff, black)
4. Если красный крест ❌ - посмотреть логи и исправить

### Шаг 6.4: Смерджить PR (триггер деплоя)

```bash
# Через gh CLI
gh pr merge --merge --delete-branch

# Или через веб-интерфейс GitHub: нажать "Merge pull request"
```

### Шаг 6.5: Мониторинг автоматического деплоя

**В GitHub Actions**:

1. Открыть https://github.com/konstantinbalakin/telegram-voice2text-bot/actions
2. Найти workflow **"Build and Deploy"**
3. Кликнуть на запущенный workflow

**Что должно произойти** (~8-10 минут):

1. **Build Job** (~5-7 мин):
   - Export requirements.txt
   - Build Docker image
   - Push to Docker Hub с тегами `latest` и `${commit-sha}`

2. **Deploy Job** (~2-3 мин):
   - SSH в VPS
   - Pull новый Docker image
   - Создать `.env` с production конфигурацией
   - Запустить `docker compose up -d`
   - Проверить health check
   - Cleanup старых images

### Шаг 6.6: Проверка на VPS

**Подключиться к VPS**:

```bash
# На локальном компьютере
ssh -i ~/.ssh/telegram_bot_deploy root@YOUR_VPS_IP

# На VPS
cd /opt/telegram-voice2text-bot

# Проверить статус контейнера
docker compose -f docker-compose.prod.yml ps

# Должно показать:
# NAME                      STATUS        PORTS
# telegram-voice2text-bot   Up (healthy)

# Посмотреть логи (последние 50 строк)
docker compose -f docker-compose.prod.yml logs --tail=50 bot

# Логи в реальном времени
docker compose -f docker-compose.prod.yml logs -f bot

# Остановить логи: Ctrl+C
```

**Что искать в логах**:
- ✅ `INFO:telegram.ext.Application:Application started`
- ✅ `INFO:__main__:Bot started successfully in polling mode`
- ✅ Модель Whisper загружена (может занять 2-5 минут при первом запуске)
- ❌ Ошибки с `ERROR:` или `CRITICAL:`

### Шаг 6.7: Тестирование бота в Telegram

1. Открыть бота в Telegram (по ссылке от @BotFather)
2. Отправить `/start`
   - Должен ответить приветственным сообщением
3. Отправить **короткое** голосовое сообщение (5-10 секунд)
4. Дождаться транскрипции (~2-5 секунд для 7-секундного аудио)
5. Проверить точность транскрипции

**Если бот не отвечает**:
- Проверить логи на VPS: `docker compose logs -f bot`
- Убедиться что `TELEGRAM_BOT_TOKEN` правильный
- Проверить что контейнер running: `docker ps`

---

## Фаза 6.5: Работа с миграциями базы данных (5-10 минут)

### Что такое миграции?

Миграции — это версионируемые изменения схемы базы данных. Проект использует **Alembic** для управления миграциями.

**Важно**: Миграции применяются **автоматически** при каждом деплое через GitHub Actions.

### Автоматическое применение миграций

При каждом деплое на main ветку происходит:

1. **test-migrations job**: Тестирует миграции в CI
2. **build job**: Собирает Docker image
3. **migrate job**: Применяет миграции на VPS **перед** запуском нового кода
4. **deploy job**: Обновляет и перезапускает бот

**Если миграция падает**:
- Автоматический откат к предыдущей версии схемы
- Деплой останавливается
- Бот продолжает работать на старой версии

### Проверка статуса миграций на VPS

**Проверить текущую версию схемы БД**:

```bash
# На VPS
cd /opt/telegram-voice2text-bot

# Показать текущую ревизию миграции
docker run --rm \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/alembic:/app/alembic \
  -v $(pwd)/alembic.ini:/app/alembic.ini \
  -e DATABASE_URL=sqlite+aiosqlite:////app/data/bot.db \
  konstantinbalakin/telegram-voice2text-bot:latest \
  alembic current

# Вывод: a9f3b2c8d1e4 (head)
```

**Посмотреть историю миграций**:

```bash
docker run --rm \
  -v $(pwd)/alembic:/app/alembic \
  -v $(pwd)/alembic.ini:/app/alembic.ini \
  konstantinbalakin/telegram-voice2text-bot:latest \
  alembic history
```

### Ручное применение миграций (если нужно)

**Сценарий**: CI/CD недоступен, нужно применить миграции вручную.

```bash
# На VPS
cd /opt/telegram-voice2text-bot

# 1. Обязательно сделать backup БД перед миграцией
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cp data/bot.db data/bot.db.backup_${TIMESTAMP}
ls -lh data/bot.db*  # Проверить что backup создан

# 2. Pull latest code (содержит новые миграции)
git pull origin main

# 3. Pull latest Docker image
docker pull konstantinbalakin/telegram-voice2text-bot:latest

# 4. Применить миграции
docker run --rm \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/alembic:/app/alembic \
  -v $(pwd)/alembic.ini:/app/alembic.ini \
  -e DATABASE_URL=sqlite+aiosqlite:////app/data/bot.db \
  konstantinbalakin/telegram-voice2text-bot:latest \
  alembic upgrade head

# 5. Перезапустить бота с новой версией
docker compose -f docker-compose.prod.yml restart bot

# 6. Проверить логи
docker compose -f docker-compose.prod.yml logs --tail=50 bot
```

### Откат миграции (Rollback)

**Сценарий**: Миграция применилась, но вызвала проблемы.

```bash
# На VPS
cd /opt/telegram-voice2text-bot

# 1. Остановить бота (важно!)
docker compose -f docker-compose.prod.yml stop bot

# 2. Откатить последнюю миграцию
docker run --rm \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/alembic:/app/alembic \
  -v $(pwd)/alembic.ini:/app/alembic.ini \
  -e DATABASE_URL=sqlite+aiosqlite:////app/data/bot.db \
  konstantinbalakin/telegram-voice2text-bot:latest \
  alembic downgrade -1

# 3. Проверить текущую ревизию
docker run --rm \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/alembic:/app/alembic \
  -v $(pwd)/alembic.ini:/app/alembic.ini \
  konstantinbalakin/telegram-voice2text-bot:latest \
  alembic current

# 4. Откатить Docker image к предыдущей версии
# (найти SHA предыдущего коммита в GitHub)
docker pull konstantinbalakin/telegram-voice2text-bot:<previous-sha>
docker tag konstantinbalakin/telegram-voice2text-bot:<previous-sha> \
           konstantinbalakin/telegram-voice2text-bot:latest

# 5. Запустить бота с откаченной версией
docker compose -f docker-compose.prod.yml up -d bot

# 6. Проверить что все работает
docker compose -f docker-compose.prod.yml logs --tail=50 bot
```

### Health Check и миграции

После обновления health check теперь проверяет:
- ✅ Подключение к базе данных
- ✅ Версия схемы (должна быть HEAD)

**Если health check fails с ошибкой схемы**:

```bash
# Посмотреть логи
docker compose -f docker-compose.prod.yml logs bot | grep -i schema

# Обычно означает: нужно применить миграции
docker run --rm \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/alembic:/app/alembic \
  -v $(pwd)/alembic.ini:/app/alembic.ini \
  -e DATABASE_URL=sqlite+aiosqlite:////app/data/bot.db \
  konstantinbalakin/telegram-voice2text-bot:latest \
  alembic upgrade head

# Перезапустить
docker compose -f docker-compose.prod.yml restart bot
```

### Документация по миграциям

Подробные руководства:
- **Разработка**: `/docs/development/database-migrations.md` - создание миграций
- **Операции**: `/docs/deployment/migration-runbook.md` - production процедуры

---

## Фаза 7: Мониторинг ресурсов (10 минут)

### Шаг 7.1: Проверить использование памяти

**На VPS**:

```bash
# Мониторинг в реальном времени
docker stats telegram-voice2text-bot

# Выход: Ctrl+C

# Показывает:
# CONTAINER   CPU %   MEM USAGE / LIMIT   MEM %   NET I/O   BLOCK I/O
# telegram... 2.5%    450MB / 2GB         22%     ...       ...
```

**Отправьте несколько голосовых сообщений** и наблюдайте за:
- **MEM USAGE**: Пик во время транскрипции
- **CPU %**: Загрузка процессора

### Шаг 7.2: Записать фактические требования

Замерьте пик памяти при обработке голосового сообщения:

```bash
# Отправьте голосовое в Telegram (30 секунд)
# Смотрите docker stats

# Пример наблюдений:
# - Idle (без работы): ~300-400MB
# - Peak (транскрипция): ~1.8-2.2GB для medium model
```

### Шаг 7.3: Решение по масштабированию RAM

**Если пик память > 80% от доступной RAM**:
- 1GB VPS: Upgrade до 2GB (через панель провайдера)
- Обычно занимает 1-2 минуты, контейнер перезапустится автоматически

**Команда для мониторинга после upgrade**:

```bash
# Проверить что Docker перезапустился после добавления RAM
docker compose -f docker-compose.prod.yml ps

# Если stopped - запустить вручную
docker compose -f docker-compose.prod.yml up -d
```

---

## Фаза 8: Безопасность (Опционально, 20-30 минут)

### Базовая безопасность

```bash
# На VPS

# 1. Настроить UFW firewall
apt install ufw -y
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw enable

# 2. Отключить password authentication для SSH
nano /etc/ssh/sshd_config

# Изменить эти строки:
# PasswordAuthentication no
# PubkeyAuthentication yes
# PermitRootLogin prohibit-password

# Сохранить (Ctrl+X, Y, Enter) и перезапустить SSH
systemctl restart sshd

# 3. Настроить автоматические обновления безопасности
apt install unattended-upgrades -y
dpkg-reconfigure --priority=low unattended-upgrades
# Выбрать "Yes"
```

### Продвинутая безопасность

```bash
# 4. Установить fail2ban (защита от brute-force)
apt install fail2ban -y
systemctl enable fail2ban
systemctl start fail2ban

# 5. Создать non-root пользователя (если используете root)
adduser botuser
usermod -aG sudo botuser
usermod -aG docker botuser

# Скопировать SSH ключи для нового пользователя
mkdir -p /home/botuser/.ssh
cp /root/.ssh/authorized_keys /home/botuser/.ssh/
chown -R botuser:botuser /home/botuser/.ssh
chmod 700 /home/botuser/.ssh
chmod 600 /home/botuser/.ssh/authorized_keys

# Обновить VPS_USER в GitHub Secrets: root → botuser
```

---

## Troubleshooting

### Проблема: SSH connection refused

```bash
# Проверить что SSH демон работает на VPS
# (подключиться через веб-консоль провайдера)
systemctl status sshd

# Если stopped - запустить
systemctl start sshd
```

### Проблема: Docker image pull failed в деплое

```bash
# На VPS - проверить Docker Hub credentials
docker login

# Проверить что image существует
docker pull konstantinbalakin/telegram-voice2text-bot:latest
```

### Проблема: Health check failed

```bash
# Посмотреть логи контейнера
docker logs telegram-voice2text-bot

# Проверить .env файл
cat /opt/telegram-voice2text-bot/.env

# Убедиться что TELEGRAM_BOT_TOKEN правильный
```

### Проблема: Бот не отвечает после деплоя

```bash
# 1. Проверить что контейнер работает
docker ps | grep telegram-voice2text-bot

# 2. Посмотреть логи последних 100 строк
docker compose -f docker-compose.prod.yml logs --tail=100 bot

# 3. Перезапустить контейнер
docker compose -f docker-compose.prod.yml restart bot

# 4. Проверить .env токен
cat .env | grep TELEGRAM_BOT_TOKEN
```

### Проблема: Out of Memory (OOM)

```bash
# Проверить использование памяти
free -h
docker stats --no-stream

# Upgrade RAM через панель провайдера (1GB → 2GB)

# После upgrade - проверить
free -h
# Должно показать новый размер
```

---

## Полезные команды

### Управление Docker контейнером

```bash
# Логи
docker compose -f docker-compose.prod.yml logs -f bot

# Перезапуск
docker compose -f docker-compose.prod.yml restart bot

# Остановка
docker compose -f docker-compose.prod.yml stop bot

# Запуск
docker compose -f docker-compose.prod.yml up -d bot

# Удалить контейнер и пересоздать
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d

# Подключиться внутрь контейнера
docker exec -it telegram-voice2text-bot bash
```

### Мониторинг системы

```bash
# Использование диска
df -h

# Использование памяти
free -h

# Топ процессов
htop  # или top

# Docker информация
docker system df
```

### Cleanup старых Docker images

```bash
# Посмотреть все images
docker images

# Удалить старые images бота (оставить последние 2-3)
docker images konstantinbalakin/telegram-voice2text-bot --format "{{.ID}} {{.CreatedAt}}" | \
  tail -n +4 | awk '{print $1}' | xargs docker rmi

# Cleanup неиспользуемых volumes и networks
docker system prune -a --volumes -f
```

---

## Следующие шаги после успешного деплоя

1. ✅ **Мониторинг**: Следить за логами первые 24 часа
2. ✅ **Backup**: Настроить автоматический backup базы данных `./data/bot.db`
3. ⏳ **PostgreSQL**: Мигрировать с SQLite на PostgreSQL (для production масштаба)
4. ⏳ **Webhook режим**: Переключиться с polling на webhook (требует домен + SSL)
5. ⏳ **Мониторинг**: Настроить Prometheus + Grafana для метрик

---

## Контакты и поддержка

- **GitHub Issues**: https://github.com/konstantinbalakin/telegram-voice2text-bot/issues
- **Documentation**: `memory-bank/` в репозитории
- **CI/CD Plan**: `.memory-bank/plans/2025-10-17-cicd-pipeline-plan.md`

---

**Поздравляем! 🎉** Ваш бот теперь работает на VPS с автоматическим деплоем.
