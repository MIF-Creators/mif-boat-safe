# mif-boat-safe

Репозиторий с экспериментами по автономной навигации лодки.

## Актуальный production-путь

Рабочая и актуальная система находится в `system/`.

Установка из корня репозитория (Windows, Linux, Raspberry Pi одинаково):

```bash
python -m venv venv
# Windows: venv\Scripts\activate    Linux / Raspberry Pi: source venv/bin/activate
pip install -e ".[vehicle,nav,control,dev]"
```

Команда выше ставит всё для разработки. На рабочие машины ставятся только
нужные группы зависимостей из `pyproject.toml`:

| Машина | Команда |
|---|---|
| Пункт управления | `pip install -e ".[control]"` |
| Лодка (Raspberry Pi) | `pip install -e ".[vehicle,rpi]"` |
| Навигационный сервер | `pip install -e ".[nav]"` |

Группа `rpi` ставит `RPi.GPIO` и собирается только на Raspberry Pi. Без неё
лодка работает с заглушкой моторов — на лодке её не забывать.

`pip install -e .` ставит пакет `system` в режиме разработки: правки в коде
подхватываются без переустановки, импорт `system.*` работает из любого каталога.

Запуск компонентов:

| Компонент | Команда | То же через модуль (из любого каталога) |
|---|---|---|
| Пункт управления | `boat-control` | `python -m system.control_center.main` |
| Навигационный сервер | `boat-nav` | `python -m system.navigation_server.main` |
| Лодка | `boat-vehicle` | `python -m system.vehicle.main` |

Подробная инструкция по настройке, MQTT-топикам и переменным окружения находится в `system/README.md`.

## Структура репозитория

- `system/` - текущая распределенная архитектура на MQTT (control center, navigation server, vehicle runtime)
- `legacy/` - исторические прототипы и эксперименты, оставленные только для справки

## Примечание по рефакторингу

Legacy-модули перенесены из корня репозитория в `legacy/`, чтобы уменьшить шум и явно обозначить канонический путь запуска.
Список перенесенных каталогов см. в `legacy/README.md`.

## Дальнейшие улучшения

Потенциальные не ломающие улучшения, найденные во время очистки структуры, собраны в `IMPROVEMENTS.md`.
