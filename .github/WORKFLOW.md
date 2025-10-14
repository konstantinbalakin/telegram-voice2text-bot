# Git & GitHub Workflow

## Общая стратегия

Проект использует **Feature Branch Workflow** с защищенной main веткой.

## Структура веток

```
main (защищенная, только через PR)
  ↑
  ├── feature/database-models
  ├── feature/whisper-service
  ├── feature/bot-handlers
  ├── feature/queue-system
  └── feature/integration-tests
```

## Workflow для разработки

### 1. Начало работы над новой фичей

```bash
# Убедитесь, что main актуальная
git checkout main
git pull origin main

# Создайте feature ветку
git checkout -b feature/database-models
```

### 2. Работа в feature ветке

```bash
# Делайте коммиты по мере работы
git add <files>
git commit -m "feat: add User model with quota fields"

# Пушьте в GitHub регулярно (для backup и видимости прогресса)
git push origin feature/database-models
```

### 3. Коммиты

**Формат**: Используем [Conventional Commits](https://www.conventionalcommits.org/)

```
<type>: <description>

[optional body]
```

**Типы коммитов**:
- `feat:` - новая функциональность
- `fix:` - исправление бага
- `refactor:` - рефакторинг без изменения функциональности
- `docs:` - изменения в документации
- `test:` - добавление/изменение тестов
- `chore:` - рутинные задачи (зависимости, конфиги)
- `style:` - форматирование кода

**Примеры**:
```bash
git commit -m "feat: implement User and Usage SQLAlchemy models"
git commit -m "test: add database repository tests"
git commit -m "fix: correct quota calculation for daily reset"
git commit -m "docs: update Memory Bank with Phase 2 progress"
git commit -m "refactor: extract quota logic to separate service"
```

### 4. Публикация коммитов

**Регулярно пушьте в GitHub**:
```bash
# После каждого значимого коммита или группы коммитов
git push origin feature/database-models
```

Это дает:
- ✅ Backup вашей работы
- ✅ Видимость прогресса
- ✅ Возможность продолжить с другой машины

### 5. Обновление документации (перед PR)

**ВАЖНО**: Перед созданием PR обновите документацию:

```bash
# После завершения кода и тестов, обновите документацию
# Memory Bank: activeContext.md, progress.md (если значимые изменения)
# README.md: если изменился API или добавились новые возможности
# .env.example: если добавились новые настройки

# Сделайте отдельный коммит с документацией
git add .claude/memory-bank/*.md README.md .env.example
git commit -m "docs: update documentation after Phase X completion"
git push origin feature/database-models
```

**Зачем это нужно**:
- PR содержит полную картину: код + тесты + документация
- Документация синхронизирована с кодом
- Будущие разработчики видят актуальное состояние
- Memory Bank обновлен для следующей сессии Claude Code

### 6. Создание Pull Request

Когда фича готова (код + тесты + документация):

```bash
# Создайте Pull Request через GitHub CLI
gh pr create --title "feat: implement database models and repositories" \
  --body "$(cat <<'EOF'
## Summary
- Implemented SQLAlchemy models: User, Usage, Transaction
- Added Alembic migrations
- Implemented repository pattern with async methods
- Added comprehensive tests (85% coverage)
- Updated Memory Bank and documentation

## Test plan
- [x] All unit tests pass
- [x] Migrations run successfully
- [x] Repository CRUD operations work
- [x] No type errors (mypy clean)

## Related
- Closes Phase 2.1 from implementation plan
- Next: Whisper service integration
EOF
)"
```

### 7. Code Review и Auto-Merge

**Автоматический мерж** (рекомендуется для solo-разработки):

```bash
# Сразу после создания PR, автоматически мержим его
gh pr merge <PR_NUMBER> --merge --delete-branch

# Или можно настроить auto-merge на GitHub:
gh pr merge <PR_NUMBER> --auto --merge --delete-branch
```

**Ручной процесс** (если нужен review):

1. **Review**: Проверьте PR (или попросите кого-то)
2. **Tests**: Убедитесь что CI/CD пройден (когда настроим)
3. **Merge**: Влейте в main через GitHub веб-интерфейс
4. **Cleanup**: Удалите feature ветку

```bash
# После мержа PR в GitHub
git checkout main
git pull origin main
git branch -d feature/database-models  # Удалить локально
```

**Преимущества auto-merge**:
- ✅ Быстрый workflow для solo-разработки
- ✅ PR история сохраняется
- ✅ Автоматическая очистка feature веток
- ✅ Меньше ручных операций

## Частые сценарии

### Синхронизация с main во время работы

Если main обновился, пока вы работали:

```bash
git checkout main
git pull origin main
git checkout feature/your-feature
git rebase main  # или git merge main
```

### Быстрый коммит + пуш

```bash
git add .
git commit -m "feat: add whisper model initialization"
git push
```

### Исправление последнего коммита

```bash
# Если забыли добавить файлы или опечатка в сообщении
git add <forgotten-files>
git commit --amend
git push --force-with-lease  # Осторожно! Только если никто не использует вашу ветку
```

## Этапы работы по проекту

### Phase 2: Database & Whisper
- **Ветка**: `feature/database-models`
  - Коммиты: модели → миграции → репозитории → тесты
  - PR: "feat: implement database layer"

- **Ветка**: `feature/whisper-service`
  - Коммиты: WhisperService → AudioHandler → тесты
  - PR: "feat: add Whisper transcription service"

### Phase 3: Processing Queue
- **Ветка**: `feature/queue-system`
  - Коммиты: QueueManager → Workers → Task models
  - PR: "feat: implement async processing queue"

### Phase 4: Bot Handlers
- **Ветка**: `feature/bot-handlers`
  - Коммиты: commands → voice handler → middleware
  - PR: "feat: add Telegram bot handlers"

### Phase 5: Integration
- **Ветка**: `feature/integration`
  - Коммиты: связка компонентов → e2e тесты
  - PR: "feat: integrate all components"

### Phase 6: Docker
- **Ветка**: `feature/docker-deployment`
  - Коммиты: Dockerfile → docker-compose → docs
  - PR: "feat: add Docker deployment"

## GitHub настройки (рекомендации)

### Защита main ветки

После создания репозитория на GitHub:

1. Settings → Branches → Add rule
2. Branch name pattern: `main`
3. Включить:
   - ✅ Require pull request before merging
   - ✅ Require approvals: 0 (для solo-разработки с auto-merge)
   - ✅ Dismiss stale PR approvals when new commits are pushed
   - ✅ Require status checks to pass (когда настроим CI/CD)

**Примечание**: Для solo-разработки с auto-merge установите "Require approvals: 0", чтобы можно было мержить PR без ожидания review.

### Auto-Merge Configuration

**Способ 1: Через GitHub CLI** (рекомендуется)
```bash
# После создания PR
gh pr merge <PR_NUMBER> --merge --delete-branch

# Или с автоматическим ожиданием проверок
gh pr merge <PR_NUMBER> --auto --merge --delete-branch
```

**Способ 2: Включить Auto-Merge в GitHub Settings**
1. Settings → General → Pull Requests
2. ✅ Allow auto-merge
3. При создании PR: нажмите "Enable auto-merge"

**Способ 3: GitHub Actions** (для автоматизации)
```yaml
# .github/workflows/auto-merge.yml
name: Auto-merge
on:
  pull_request:
    types: [opened, ready_for_review]

jobs:
  auto-merge:
    runs-on: ubuntu-latest
    if: github.actor == 'konstantinbalakin'  # Только для владельца
    steps:
      - uses: pascalgn/automerge-action@v0.15.6
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          MERGE_LABELS: ""
          MERGE_METHOD: "merge"
```

**Когда использовать auto-merge**:
- ✅ Solo-разработка (вы единственный разработчик)
- ✅ Все тесты проходят автоматически
- ✅ Нужен быстрый workflow
- ❌ Командная разработка (нужен code review)
- ❌ Критичные изменения (требуют проверки)

### Labels для PR

Создайте labels:
- `phase-1`, `phase-2`, etc. - этапы разработки
- `database`, `whisper`, `bot`, `queue` - компоненты
- `bug`, `enhancement`, `documentation`
- `ready-for-review`, `work-in-progress`

## Полезные команды

```bash
# Показать все ветки
git branch -a

# Показать текущую ветку
git branch --show-current

# Удалить ветку
git branch -d feature/old-feature

# Показать коммиты с графом
git log --oneline --graph --decorate

# Показать изменения перед коммитом
git diff --staged

# Отменить изменения в файле
git restore <file>

# Отменить staging
git restore --staged <file>
```

## Slash команда /commit

Используйте `/commit` для автоматического создания коммита:
- Claude проанализирует изменения
- Создаст осмысленное commit message
- Запустит git commit

Для пуша выполните вручную:
```bash
git push origin <branch-name>
```

## Пример полного цикла

```bash
# 1. Создать ветку
git checkout -b feature/database-models

# 2. Работать и коммитить
git add src/storage/models.py
git commit -m "feat: add User and Usage models"
git push origin feature/database-models

git add src/storage/repositories.py
git commit -m "feat: implement repository pattern"
git push

git add tests/unit/test_repositories.py
git commit -m "test: add repository unit tests"
git push

# 3. Обновить документацию (ВАЖНО!)
git add .claude/memory-bank/activeContext.md .claude/memory-bank/progress.md README.md
git commit -m "docs: update Memory Bank and README after Phase 2.1 completion"
git push

# 4. Создать PR
gh pr create --title "feat: implement database layer" --body "..."

# 5. Auto-merge (рекомендуется)
gh pr merge <PR_NUMBER> --merge --delete-branch

# 6. Обновить main локально
git checkout main
git pull origin main
```

## Следующие шаги

1. **Сейчас**: Закоммитить текущие изменения (реорганизация Memory Bank)
2. **Создать GitHub репозиторий** и добавить remote
3. **Запушить main** ветку
4. **Создать первую feature ветку** для Phase 2
5. **Настроить защиту main** через GitHub Settings

## Вопросы?

- Хотите упрощенный workflow без PR? (коммит → пуш напрямую в main)
- Нужен CI/CD с автоматическими тестами при PR?
- Работаете один или с командой?
