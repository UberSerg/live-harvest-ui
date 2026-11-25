# Visual / interaction review — Live Harvest UI v0.4

Дата: 2026-11-25  
Инструмент: Cursor browser + CDP `performance.now` на click-path

## Причина лагов Universe (v0.3)

1. `universeSVG(id)` пересоздавал весь SVG на каждый клик.
2. `bindUniverse()` вешал новые listeners после каждого клика (рекурсия).
3. `detail.outerHTML = ...` сносил узел панели.
4. CSS `transform: scale()` на `<g transform="translate(...)">` конфликтовал с SVG-transform → визуальные скачки / «дёрганье».

## Что исправлено

- SVG монтируется один раз (`UniverseController`).
- Delegation click/keydown на host; active = class + `aria-pressed`.
- Detail обновляется без сноса SVG.
- Hover/focus только на `circle.leaf` (stroke/fill), не transform группы.
- Клавиатура: Enter/Space, стрелки; `prefers-reduced-motion`.
- Навигация: 3 экрана; stubs в «Позже».
- Композиция: редакционный поток вместо bento; progressive disclosure.

## Измерение кликов (не FPS)

40 последовательных `click` по узлам (synthetic MouseEvent):

| metric | value |
|---|---|
| avg | 0.28 ms |
| p50 | 0.20 ms |
| p95 | 0.60 ms |
| max | 0.80 ms |
| svgCount после | 1 |
| nodeCount после | 7 |

FPS hover не измерялся (нет стабильного frame counter в среде) — цифры FPS не выдумывались.  
Ручная проверка: клик Финансы → деталь меняется; ArrowRight Семья→Финансы; повторный вход на экран без накопления SVG.

## Скриншоты

- `lh-v04-home-1440.png`
- `lh-v04-personality-1440.png`
- `lh-v04-universe-1440.png`
- `lh-v04-home-mobile.png`

## Честная оценка

Лучше v0.3 по лагу и по анти-dashboard композиции.  
Не объявляется «премиум-победой»: орбита всё ещё простая; нет уникальной иллюстративной сигнатуры; personality — сильный текст, но мало визуального ритма; mobile — top-stack nav.

## Оставшиеся недостатки

- Вселенная визуально минимальна (7 узлов на кольце).
- Нет реального wiring к `harvest/*.md`.
- Mobile nav не drawer.
- Вторичный контент в `<details>` всё ещё «серые списки».
