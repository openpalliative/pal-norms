# pal-norms: как выпустить

Раздел для общего `RELEASE.md`. pal-norms пушится **первым** из шести репо: из его `data/v1/` берут нормы, сроки и календарь pal-devices-data, pal-directory, obrashchenie-kit, home-care-kit и хаб

## 1. До первого пуша

1. Включить Pages из Actions, иначе первый `pages.yml` упадёт на `deploy-pages`:

   ```sh
   gh api -X POST repos/openpalliative/pal-norms/pages -f build_type=workflow
   ```

   Если Pages уже включены из ветки: `gh api -X PUT repos/openpalliative/pal-norms/pages -f build_type=workflow`

2. Разрешить Actions создавать PR. Без этого наблюдатель не сможет прислать черновик календаря (`create-pull-request` падает с ошибкой прав). В org и в репо: Settings > Actions > General > Workflow permissions > «Allow GitHub Actions to create and approve pull requests». Права по умолчанию оставить «Read repository contents»: каждому workflow нужные права выданы в самом файле

   ```sh
   gh api -X PUT orgs/openpalliative/actions/permissions/workflow -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true
   gh api -X PUT repos/openpalliative/pal-norms/actions/permissions/workflow -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true
   ```

3. Метки. Наблюдатель и формы issue ставят `review:data` и `review:legal`. Без меток issue всё равно создаётся, но его не найти фильтром:

   ```sh
   gh label create review:data --color C9A26B --description "Данные: сверить со сканом" --repo openpalliative/pal-norms --force
   gh label create review:legal --color 7A4A2E --description "Толкование: нужен юрист в РФ" --repo openpalliative/pal-norms --force
   ```

   Полный список меток для всех репо ставит `scripts/labels` из хаба

4. Security: включить private vulnerability reporting (на него ссылаются `SECURITY.md`, `CODE_OF_CONDUCT.md` и форма issue), secret scanning, push protection, Dependabot alerts:

   ```sh
   gh api -X PUT repos/openpalliative/pal-norms/private-vulnerability-reporting
   ```

## 2. Пуш и первая проверка

1. Запушить main. Сработают `checks.yml` (actionlint и ворота целиком, браузерные тесты в трёх движках) и `pages.yml`
2. Дождаться зелёного `pages` и проверить живой сайт:
   - https://openpalliative.github.io/pal-norms/ открывается, в подвале версия данных
   - https://openpalliative.github.io/pal-norms/data/v1/index.json отдаёт 9 наборов
   - https://openpalliative.github.io/pal-norms/indications/ показывает заглушку «Страница ждёт проверки медиком и юристом в РФ», пока в `content/gates.yaml` стоит `indications_public: false`
   - несуществующий адрес внутри `/pal-norms/` отдаёт свою 404
3. Только после этого пушить соседей и запускать у них `sync-data`

## 3. Наблюдатель pravo.gov.ru

`watch.yml` по понедельникам, а в сентябре каждый день, спрашивает API publication.pravo.gov.ru о поправках, новых актах и постановлении о переносе выходных

1. **Первый запуск вручную**, сразу после пуша: `gh workflow run watch.yml --repo openpalliative/pal-norms`. В логе шага `watch` будет «Проверка прошла» или «не прошла». Записать в общий отчёт, отвечает ли pravo.gov.ru раннерам GitHub
2. Если прошла: коммит `data: снимок pravo.gov.ru <дата>` в main, после него `watch.yml` сам запускает `pages.yml`, и на сайте обновляется «Последняя проверка новых публикаций» и предупреждение об истекающих актах (за 120 дней)
3. Если `main` защищён и требует PR, прямой коммит снимка не пройдёт. Два варианта: в ruleset main добавить в обход приложение GitHub Actions только для этого репо, или ничего не менять и раз в месяц запускать `scripts/watch-local` (снимок тогда коммитит мейнтейнер)
4. Расписание GitHub выключает в публичных репо после 60 дней без активности, и коммит бота от этого не спасает. Поэтому последний шаг `watch.yml` (с `if: always()`) включает workflow обратно через `PUT .../actions/workflows/watch.yml/enable`. Раз в месяц всё равно стоит открыть вкладку Actions и проверить, что `watch` не выключен
5. Черновик календаря приходит PR из ветки `watch/<дата>` с меткой `review:data`. PR от бота не запускает проверки сам, поэтому `watch.yml` запускает `checks.yml` на ветке PR через `gh workflow run`. Мерж только после сверки дат со сканом
6. Всё юридически значимое (новый акт, поправка, отмена, переопубликование, недоступность портала три раза подряд) приходит issue с заголовком `[watch:...]`

### WATCH_RUNNER

Если pravo.gov.ru не пускает раннеры GitHub, есть два пути:

- **по умолчанию:** мейнтейнер раз в месяц запускает `sh scripts/watch-local` (нужны uv и `gh auth login`). Результат тот же: снимок, черновики в `data/`, issues
- **свой раннер:** переменная репо `WATCH_RUNNER` с JSON-строкой, например `'["self-hosted","linux","pravo"]'`. Пустая переменная значит `"ubuntu-24.04"`. Требования: git, gh, uv, `poppler-utils`, `tesseract-ocr`, `tesseract-ocr-rus` (если их нет и это Linux, workflow ставит их через `apt-get`, нужен sudo). Раннер только на уровне этого репо, ephemeral, в репо нет workflow на `pull_request_target`, в настройках «Require approval for all outside collaborators». Включать только по решению мейнтейнера. Раннер в РФ ставит и обслуживает мейнтейнер в РФ

```sh
gh variable set WATCH_RUNNER --repo openpalliative/pal-norms --body '["self-hosted","linux","pravo"]'
```

## 4. Защита main

Ruleset на main: изменения через PR, обязательные проверки `gate` и `actionlint` из `checks.yml`, без обязательного ревью CODEOWNERS, пока мейнтейнер один. Для снимка наблюдателя см. п. 3.3

## 5. Релиз

Тег `v<версия данных>`, например `v2026.10.11`:

```sh
git tag v2026.10.11 && git push origin v2026.10.11
```

`release.yml` собирает сайт так же, как Pages (`OP_TARGET=pages`, страница показаний закрыта), и кладёт в релиз:

- `pal-norms-<тег>-site.zip`: весь сайт для зеркала
- `pal-norms-<тег>-data.zip`: `data/v1/*.json` со схемами
- `pal-norms-<тег>-data.sqlite`: те же наборы одной базой SQLite, таблица на набор, плюс `datasets` и `sources`
- `SHA256SUMS`

Проверить скачанное: `sha256sum -c SHA256SUMS`

## 6. Оформление репо

```sh
gh repo edit openpalliative/pal-norms \
  --description "Нормы о паллиативной помощи с дословными цитатами из официальных публикаций и калькулятор сроков" \
  --homepage https://openpalliative.github.io/pal-norms/ \
  --add-topic palliative-care --add-topic open-data --add-topic russia --add-topic regulations --add-topic deadline-calculator
```

Social preview вручную: Settings > General > Social preview, файл `docs/social-preview.png` (1280 x 640)

## 7. Проверено локально

- actionlint 1.7.12 с shellcheck 0.10.0 по 4 workflow: 0 замечаний
- zizmor `--offline`: 0 замечаний
- пины действий сверены `git ls-remote` 11.10.2026: checkout v7.0.1, setup-uv v10.3.0, pnpm/action-setup v6.1.0, setup-node v7.1.0, upload-artifact v7.0.2, upload-pages-artifact v5.0.0, deploy-pages v5.0.1, create-pull-request v8.1.1
- сборка как в релизе и как в Pages совпадает файл в файл, кроме меток времени сборки
