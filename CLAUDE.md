# Проект: каркасные дома по СП 31-105-2002

Моделирование деревянных каркасных (платформенных) домов в Blender на основе
**СП 31-105-2002 «Проектирование и строительство энергоэффективных одноквартирных жилых
домов с деревянным каркасом»**.

## Главное

Для любой задачи про каркас, стропилку, перекрытие, сечения, пролёты или модель в Blender —
**вызывай скилл `karkas-blender`**. В нём готовый параметрический генератор и машиночитаемые
таблицы СП. Не считай пролёты «по памяти» и не пиши генератор заново.

## Структура

```
SP-31-105-2002.pdf                      оригинал свода правил
docs/sp31105-full.txt                   полный текст для grep (маркеры ===== PAGE N =====)
out/current.blend                       ЖИВАЯ модель — она открыта в Blender
out/current.json                        её спецификация
out/                                    прочие результаты: .png, отчёты, ведомости
tools/karkas_autoreload.py              аддон автоперезагрузки .blend
tools/install_autoreload.sh             установка аддона
.claude-plugin/                         манифесты плагина Claude Code
commands/                               слэш-команды /karkas-sp31105:build и :check
.claude/skills/karkas-blender           симлинк -> skills/karkas-blender
skills/karkas-blender/
    SKILL.md                            как пользоваться (формат спецификации, что проверяется)
    references/01..06-*.md              выжимка норм по разделам + все таблицы Приложения Б
    scripts/build_house.py              CLI
    scripts/karkas/rules.py             таблицы СП в машиночитаемом виде + подбор сечений
    scripts/karkas/model.py             spec -> каркас + отчёт о соответствии
    scripts/karkas/geom.py              элемент каркаса (брус)
    scripts/karkas/build.py             построение в Blender, камера, рендер
    scripts/selftest.py                 самопроверка таблиц и генератора
    examples/dom_9x7.json               рабочий пример

Каталог `skills/karkas-blender/` самодостаточен: переносится в другой проект,
в `~/.claude/skills/` или ставится плагином целиком (см. README).
```

## Окружение

- Blender: `/Applications/Blender.app/Contents/MacOS/Blender` (4.5 LTS, Python 3.11).
- `rules.py` / `model.py` — чистый Python, работают и без Blender (режим `--check`).
- Результаты пиши в `out/`, временные файлы — в scratchpad, не в корень проекта.

## Живая модель

Рабочая модель всегда лежит в **`out/current.blend`**, её спецификация — **`out/current.json`**.
Пересобирай ТУДА ЖЕ:

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b \
    --python .claude/skills/karkas-blender/scripts/build_house.py -- \
    --spec out/current.json --out out/current --open
```

Открытый Blender перечитает файл сам — в нём включён аддон `karkas_autoreload`
(`tools/karkas_autoreload.py`), он следит за mtime и делает revert. Флаг `--open`
запускает Blender, только если файл ещё никем не открыт. Проверить, что перезагрузка
прошла: `tail ~/.cache/karkas/autoreload.log`.

Если в сцене есть несохранённые правки, аддон перезагрузку пропускает и пишет об этом —
тогда File > Revert вручную.

**Не создавай новых имён файлов для той же модели** (`_v2`, `_fixed` и т. п.) — иначе
у пользователя в Blender останется открытым старый. Меняешь спецификацию — правь
`out/current.json` и пересобирай в `out/current`.

## Правила работы

- Сначала `--check` (секунды), потом Blender. Не рендерь, пока в отчёте есть `✗`.
- После любой правки кода генератора **пересобери `out/current`**, иначе у пользователя
  в Blender останется устаревшая модель.
- Все строки `✗` и `!` из `_report.txt` пересказывай пользователю — это нарушения норм.
- Ссылайся на конкретные пункты и таблицы СП («табл. Б-6», «п. 7.2.13»), а не «по нормам».
- Размеры: сечения в мм (`38x140`), пролёты и координаты в метрах.
- Язык общения и названий объектов в модели — русский.
