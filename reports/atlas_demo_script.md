# Atlas demonstration, 60 seconds

A live demonstration during slide 13, in place of its second half. The committee sees the tool that the conclusion recommends, working on real data.

## Before the defence

1. Copy `dashboard/offline/astana_access_atlas.html` to the laptop desktop and to a USB stick. It is one file with all data inside and opens by double click, without internet or a server. Rebuild it after any change with `python scripts/build_offline_atlas.py`.
2. Open it once in the browser you will present from, press F11 for full screen and P for the large-screen mode, then open the Site screening view so it is cached and ready.
3. Light theme reads best on a projector: add `?theme=light` to the address, for example `astana_access_atlas.html?theme=light#screening`.
4. Keep the slides and the atlas in two windows and switch with Alt+Tab. Rehearse the switch twice.
5. Fallback: if the laptop or projector fails, Figure 3.9 of the thesis (`fig:atlas`; check the number in the compiled PDF) shows the same screen; say "the same screen is Figure 3.9 in the thesis" and continue with slide 14.

## Script (English)

| Time | Action | Words |
|---|---|---|
| 0-10 s | Alt+Tab to the atlas, Site screening open, 1 km selected | "This is the screening tool from the last stage of our pipeline. Blue blocks are children with no state school within a kilometre on foot; green rings are the 238 school sites already reserved in the detailed plans." |
| 10-25 s | Point to the gold circles and the two big numbers | "The gold sites are the 17 that reach the most of these children, ranked in order. Together they reach 28,920 children; the 17 new schools of the city's plan, the violet diamonds, reach 11,904." |
| 25-40 s | Drag the slider from 17 to 5, then back to 17 | "The order matters: the first five sites alone already reach more children than the whole plan." |
| 40-50 s | Click one green ring to add it, point to the list | "A planner can add or remove any site and see at once how many children it adds." |
| 50-60 s | Alt+Tab back to the slides | "The full ranking of all 238 sites is exported as a table, so the city can use it directly." |

Check the claim about five sites on the day: with the slider at 5 the gold number must exceed 11,904. On the present data the first five reach 12,590.

## Сценарий (русский)

| Время | Действие | Слова |
|---|---|---|
| 0-10 с | Alt+Tab в атлас, открыт Site screening, выбран 1 км | «Это инструмент отбора участков, последний этап нашего конвейера. Синие кварталы — дети, у которых нет государственной школы в пределах километра пешком; зелёные кольца — 238 участков под школы, уже зарезервированных в ПДП.» |
| 10-25 с | Показать золотые кружки и две большие цифры | «Золотые — это 17 участков, которые охватывают больше всего таких детей, с номерами по очереди. Вместе они охватывают 28 920 детей; 17 новых школ городского плана, фиолетовые ромбы, — 11 904.» |
| 25-40 с | Перетащить ползунок с 17 на 5, затем обратно на 17 | «Очерёдность важна: уже первые пять участков охватывают больше детей, чем весь план.» |
| 40-50 с | Кликнуть по зелёному кольцу, показать список | «Планировщик может добавить или убрать любой участок и сразу увидеть, сколько детей он добавляет.» |
| 50-60 с | Alt+Tab обратно в слайды | «Полный рейтинг всех 238 участков выгружается таблицей, так что город может использовать его напрямую.» |

Перед защитой проверь утверждение про пять участков: при ползунке на 5 золотая цифра должна быть больше 11 904. На текущих данных первые пять участков дают 12 590.
