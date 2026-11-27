"""Собирает правдоподобный прогон для вёрстки и тестов стенда. Все компании вымышлены."""

import hashlib
import random
from collections import Counter
from pathlib import Path

import yaml

from bizmodel.schemas import (
    Advice,
    AgentCall,
    BusinessModel,
    Card,
    Company,
    ControlSample,
    Cost,
    Decision,
    Evidence,
    Failure,
    Funnel,
    Gate,
    GoldenScore,
    Isolation,
    Objection,
    OutageDrill,
    Passport,
    Prescreen,
    Rubric,
    Run,
    TestSketch,
    TreeResult,
    Trust,
    ValidatorStats,
    Violation,
    Vote,
)

ROOT = Path(__file__).resolve().parents[2]
rng = random.Random(7)
TODAY = "2026-11-26"
FOREST_VERSION = "3f9c2a71"
VOTERS = [
    "google/gemma-4-26b-a4b-it",
    "meta-llama/llama-4-maverick",
    "mistralai/mistral-small-2603",
    "deepseek/deepseek-v4.1-flash",
    "openai/gpt-6-luna",
    "claude-sonnet-5-5",
]
QUORUM = 5

TREES = [
    ("online", "Законно и полностью онлайн, без своей лицензии", "all", [
        ("legal", "Деятельность законна", "yes", "E3"),
        ("fully_online", "Продаётся и оказывается полностью онлайн", "yes", "E1"),
        ("own_license", "Нужна своя лицензия до первого клиента", "no", "E5"),
    ]),
    ("recurring", "Деньги повторяются", "any", [
        ("subscription", "Подписка или регулярная плата", "yes", "E2"),
        ("commission", "Комиссия с регулярных операций", "yes", "E2"),
    ]),
    ("money_risk", "Без кредита, страховки и хранения чужих денег", "all", [
        ("lends", "Сам выдаёт кредиты", "no", "E3"),
        ("insures", "Несёт страховой риск", "no", "E3"),
        ("holds_funds", "Хранит чужие деньги", "no", "E3"),
    ]),
    ("not_trading_gov", "Не трейдинг и не государственный сервис", "all", [
        ("trading", "Доход от трейдинга", "no", "E1"),
        ("gov_service", "Государственный сервис", "no", "E1"),
    ]),
    ("proven_scale", "Есть компания с такой моделью от $300 млн", "all", [
        ("named_analog", "Названа компания с такой же моделью", "yes", "E4"),
        ("size_evidence", "Её размер от $300 млн подтверждён", "yes", "E4"),
    ]),
]  # fmt: skip

QUOTES = {
    "legal": "The service is offered under standard commercial terms in the United States.",
    "fully_online": "Sign up online and get started in minutes, no installation required.",
    "own_license": "We are a software provider and do not offer regulated professional services.",
    "subscription": "Plans start at $149 per month, billed monthly or annually.",
    "commission": "A 3% fee applies to every order processed through the platform.",
    "lends": "We do not extend credit or originate loans.",
    "insures": "The company is not an insurer and does not underwrite risk.",
    "holds_funds": "Payments are processed by a licensed third-party provider.",
    "trading": "Revenue comes from software subscriptions.",
    "gov_service": "Our customers are private businesses.",
    "named_analog": "The category leader sells the same subscription to the same buyer.",
    "size_evidence": "The company was valued at $1.2 billion in its latest funding round.",
}

FAIL_REASONS = {
    "legal": "Деятельность запрещена на домашнем рынке.",
    "fully_online": "В продукт входит физическое устройство, которое отправляют клиенту.",
    "own_license": "Без своей лицензии нельзя обслужить первого клиента.",
    "commission": "Платёж разовый: нет ни подписки, ни комиссии с регулярных операций.",
    "lends": "Компания выдаёт займы от своего имени.",
    "insures": "Компания сама несёт страховой риск.",
    "holds_funds": "Компания принимает деньги клиентов на свои счета до перевода получателям.",
    "trading": "Доход зависит от собственной торговли на бирже.",
    "gov_service": "Услуга оказывается по государственному заказу.",
    "named_analog": "Компании с такой же моделью не найдено.",
    "size_evidence": "Найденная компания заметно меньше $300 млн.",
}

RUBRICS = [
    ("time_to_test", "Скорость до работающего теста", 25, [
        "Без данных клиента продукт не показать, подготовка займёт больше двух месяцев.",
        "Нужны две-три интеграции с системами клиента, тест займёт 6-8 недель.",
        "Рабочий тест собирается за 3-4 недели на готовых моделях и одной интеграции.",
    ]),
    ("customer_access", "Доступ к первым клиентам", 25, [
        "Выход на покупателя только через партнёров или закупку, холодный контакт не работает.",
        "Покупателя видно, но решение принимают двое-трое, сделка длится 4-6 недель.",
        "Покупатель есть в открытых каталогах и отвечает на письмо, решает один человек.",
    ]),
    ("time_to_payment", "Скорость первой оплаты", 20, [
        "Оплата после закупочной процедуры и проверки безопасности, раньше трёх месяцев не ждать.",
        "Первый счёт после пилота на 2-4 недели, оплата по договору.",
        "Оплата картой с первого дня, чек не требует согласований.",
    ]),
    ("demand_proof", "Доказанность спроса", 10, [
        "Аналог спорный: совпадает плательщик, но не частота оплаты.",
        "Аналог найден, его размер подтверждён одной публикацией в прессе.",
        "Есть крупная компания с той же схемой оплаты, цены конкурентов открыты.",
    ]),
    ("barriers", "Барьеры и зависимости", 10, [
        "Нужны данные и согласие третьей стороны, без партнёра продукт не запускается.",
        "Работа держится на API одной платформы, условия доступа могут измениться.",
        "Нет зависимости от одной платформы и нет требований регулятора сверх обычных.",
    ]),
    ("objections", "Возражения, устоявшие после проверки", 10, [
        "Устояли два сильных возражения, оба подтверждены источником.",
        "Устояло одно возражение средней силы.",
        "После проверки источников не устояло ни одно сильное возражение.",
    ]),
]  # fmt: skip

# name, one_liner, industry, payer, pays_for, frequency, revenue_type
SELECTED = {
    "tallybook": ("Tallybook", "AI bookkeeping that reconciles invoices for small agencies", "B2B", "Агентства и студии до 30 человек", "Автоматическая сверка счетов и подготовка отчётности", "Ежемесячно, тариф за юрлицо", "subscription"),
    "chartwell": ("Chartwell Notes", "Ambient AI scribe that writes visit notes for outpatient clinics", "Healthcare", "Частные клиники на 5-20 врачей", "Автоматическое оформление записей приёма", "Ежемесячно, за каждого врача", "subscription"),
    "fieldnote": ("Fieldnote", "Voice agent that answers calls and books jobs for home service companies", "B2B", "Сервисные компании: сантехника, отопление, электрика", "Приём звонков и запись на выезд", "Ежемесячно плюс плата за минуту разговора", "subscription"),
    "quillcase": ("Quillcase", "Client intake and case triage for small law firms", "B2B", "Юридические фирмы до 15 юристов", "Приём обращений и первичный разбор дел", "Ежемесячно, за рабочее место", "subscription"),
    "roomloop": ("Roomloop", "Channel manager that syncs calendars and prices for short-term rentals", "Real Estate and Construction", "Управляющие 5-50 объектами посуточной аренды", "Синхронизация календарей и цен между площадками", "Ежемесячно, за объект", "subscription"),
    "lumenqa": ("Lumen QA", "AI agents that run regression tests for mobile apps before every release", "B2B", "Команды мобильной разработки от 5 человек", "Автоматические прогоны тестов перед релизом", "Ежемесячно, по числу прогонов", "usage_fee"),
    "dockhand": ("Dockhand", "Document automation for freight forwarders and customs brokers", "Industrials", "Небольшие экспедиторы и таможенные брокеры", "Разбор и заполнение перевозочных документов", "Ежемесячно плюс плата за документ", "subscription"),
    "benchmate": ("Benchmate", "Inventory and ordering software for research labs", "Healthcare", "Исследовательские лаборатории и биотехнологические стартапы", "Учёт реагентов и заказов", "Ежегодная подписка за лабораторию", "subscription"),
    "stockroom": ("Stockroom", "Wholesale marketplace connecting independent brands and retailers", "Consumer", "Независимые магазины и бренды", "Комиссия с каждого оптового заказа", "С каждой повторной поставки", "transaction_commission"),
    "paygrid": ("Paygrid", "Automated invoice reminders and collections for B2B suppliers", "Fintech", "Поставщики с отсрочкой платежа", "Напоминания о счетах и сбор оплат", "Ежемесячно, по числу счетов", "subscription"),
    "harborpay": ("Harborpay", "Payout platform for online marketplaces", "Fintech", "Онлайн-площадки с продавцами", "Выплаты продавцам", "Комиссия с каждой выплаты", "transaction_commission"),
    "telemend": ("Telemend", "Telehealth prescriptions for chronic conditions", "Healthcare", "Пациенты с хроническими заболеваниями", "Онлайн-приём и продление рецептов", "Ежемесячно", "subscription"),
    "kitepack": ("Kitepack", "Sensor kit and dashboard for warehouse energy monitoring", "Industrials", "Операторы складов", "Датчики и панель расхода энергии", "Ежемесячно, за склад", "subscription"),
    "novaterm": ("Novaterm", "Terminology management for technical translation teams", "B2B", "Отделы технического перевода", "Единый глоссарий и проверка терминов", "Ежемесячно, за рабочее место", "subscription"),
    "sablebase": ("Sablebase", "Compliance monitoring for accounting firms serving crypto clients", "Fintech", "Бухгалтерские фирмы с криптоклиентами", "Мониторинг операций и отчёты для регулятора", "Ежемесячно, за клиента", "subscription"),
}  # fmt: skip

# Отклонения от «всё проходит»: узел → правда или особый случай голосования.
TWISTS = {
    "stockroom": {"recurring.subscription": "no", "recurring.commission": "yes"},
    "harborpay": {
        "recurring.subscription": "no",
        "recurring.commission": "yes",
        "money_risk.holds_funds": "yes",
    },
    "telemend": {"online.own_license": "yes"},
    "kitepack": {"online.fully_online": "no"},
    "novaterm": {"proven_scale.size_evidence": "blank"},
    "sablebase": {"online.own_license": "unresolved"},
    "tallybook": {"money_risk.holds_funds": "arbiter"},
    "roomloop": {"proven_scale.size_evidence": "arbiter"},
    "benchmate": {"proven_scale.named_analog": "arbiter"},
}
TREE_REASONS = {
    ("novaterm", "proven_scale"): "Компания с такой же моделью названа, но её размер источниками не подтверждён.",
    ("sablebase", "online"): "Голоса разошлись, арбитр не смог решить, нужна ли лицензия: вопрос передан человеку.",
    ("telemend", "online"): "Продление рецептов требует медицинской лицензии в каждом штате.",
}  # fmt: skip

# levels, anchor, objections(text, reasoning, strength, verdict, quote, verifier note),
# test(channel, offer, success), upsell, advice(verdict, budget, first step, stop), trust, human
CARDS = {
    "tallybook": {
        "levels": [5, 4, 5, 4, 4, 3],
        "anchor": "Ledgerline: та же подписка для малого бизнеса, оценка $2,1 млрд по раунду 2025 года.",
        "objections": [
            ("Крупные бухгалтерские сервисы уже включают автоматическую сверку в базовый тариф.", "Если функция бесплатна у текущего поставщика, отдельная подписка теряет смысл.", 4, "supported", "Automatic reconciliation is now included in every plan at no extra cost.", "На странице тарифов это сказано прямо."),
            ("Агентства неохотно дают стороннему сервису доступ к банковской выписке.", "Без выписки сверка не работает, а подключение банка тормозит пробный период.", 3, "not_supported", "Most small firms hesitate to share passwords with new vendors.", "Опрос в источнике о передаче паролей, а не о банковских подключениях."),
            ("Ошибка в отчётности ведёт к претензиям клиента, понадобится страхование ответственности.", "Страховка добавляет расходы и месяц на оформление до первого клиента.", 3, "source_unavailable", "", "Страница не открылась при проверке."),
            ("Спрос сосредоточен перед закрытием квартала.", "Тест, запущенный в середине квартала, покажет заниженный интерес.", 2, None, "", ""),
        ],
        "test": ("Прямые письма владельцам агентств из открытых каталогов", "Сверка счетов за прошлый месяц бесплатно, дальше 149 долларов в месяц", "5 оплат из 40 пробных подключений за шесть недель"),
        "upsell": "Компаниям с базой малых агентств: банк для бизнеса, сервис выставления счетов, бухгалтерский аутсорсинг.",
        "advice": ("launch", "До 6 тысяч долларов: 4 недели разработки и 2 тысячи на рассылку", "Собрать список из 200 агентств и отправить первые 50 писем", "Меньше 3 оплат из 40 пробных подключений"),
        "trust": "high",
        "human": ["Проверить, какие банки дают подключение без партнёрского договора"],
    },
    "chartwell": {
        "levels": [4, 4, 4, 5, 3, 3],
        "anchor": "Scribewell: подписка за врача, оценка $2,8 млрд по раунду 2025 года.",
        "objections": [
            ("Записи приёма содержат медицинские данные, клиника потребует соглашение о защите данных до пилота.", "Без соглашения пилот не начнётся, а его согласование занимает недели.", 4, "supported", "Covered entities must sign a business associate agreement before sharing patient data.", "Требование подтверждено текстом регулятора."),
            ("Крупные поставщики медицинских карт встраивают собственного писаря.", "Клиника не станет платить отдельно за то, что получит в составе карты.", 4, "contradicts", "The built-in assistant is expected to reach general availability next year.", "Источник говорит о планах на следующий год, а не о готовом продукте."),
            ("Врачи возвращаются к ручным записям после первого месяца.", "Высокий отток после пробного периода обнуляет подписку.", 3, "not_supported", "Adoption stayed above 70% after ninety days in the pilot group.", "Цитата говорит об обратном: использование держится."),
        ],
        "test": ("Личные сообщения владельцам клиник через профессиональные сообщества", "Две недели бесплатно для трёх врачей, дальше 99 долларов за врача в месяц", "3 клиники платят за второй месяц"),
        "upsell": "Компаниям, у которых клиники уже в клиентах: запись на приём, телефония, расчёт зарплаты.",
        "advice": ("launch", "До 9 тысяч долларов: 6 недель разработки и оформление соглашения о данных", "Подготовить шаблон соглашения о защите данных и найти три клиники для пилота", "Ни одна из трёх клиник не оплатила второй месяц"),
        "trust": "medium",
        "human": ["Юристу: проверить требования к хранению записей приёма в выбранной стране"],
    },
    "fieldnote": {
        "levels": [4, 4, 4, 3, 4, 3],
        "anchor": "Jobline: подписка для сервисных компаний, оценка около $900 млн по публикации в прессе.",
        "objections": [
            ("Владельцы сервисных компаний не доверяют роботу первый звонок клиента.", "Первый звонок решает, достанется ли заказ, и владелец не отдаст его программе.", 4, "source_unavailable", "", "Форум, на который ссылается критик, закрыт для чтения без регистрации."),
            ("Стоимость минуты разговора съедает маржу на дешёвых тарифах.", "При длинных звонках расход на голосовую модель превышает абонентскую плату.", 3, "not_supported", "Voice minutes are billed at $0.07 with volume discounts.", "Источник называет цену минуты, но ничего не говорит о марже."),
            ("Без связи с программой диспетчеризации запись приходится переносить руками.", "Ручной перенос убирает главную выгоду: экономию времени диспетчера.", 3, "supported", "Without calendar sync, booked jobs must be re-entered manually.", "Подтверждено документацией интеграции."),
        ],
        "test": ("Звонки и сообщения владельцам из местных каталогов услуг", "Робот неделю бесплатно отвечает на пропущенные звонки, дальше 199 долларов в месяц", "4 компании из 20 оставляют робота после пробной недели"),
        "upsell": "Компаниям с базой сервисных подрядчиков: программа диспетчеризации, агрегатор заявок, поставщик запчастей.",
        "advice": ("needs_human", "До 4 тысяч долларов, но только после пяти разговоров с владельцами", "Провести пять телефонных интервью с владельцами", "Меньше двух из пяти владельцев готовы на пилот"),
        "trust": "low",
        "human": ["Спросить пятерых владельцев, отдадут ли они первый звонок роботу", "Сверить цену минуты у двух поставщиков голосовых моделей"],
        "flagged": ["12%"],
    },
    "quillcase": {
        "levels": [4, 3, 3, 4, 4, 3],
        "anchor": "Clerkly: подписка для юридических фирм, оценка $1,6 млрд по раунду 2024 года.",
        "objections": [
            ("Сервис, который отвечает на правовые вопросы, могут счесть юридической практикой без лицензии.", "Тогда модель упирается в критерий о лицензии и теряет смысл.", 4, "contradicts", "Intake software that collects facts without giving advice is not the practice of law.", "Источник прямо разделяет сбор фактов и консультацию."),
            ("Малые фирмы выбирают программы по рекомендациям, холодные письма не читают.", "Канал прямых писем не даст первых клиентов за три месяца.", 3, "supported", "Referrals remain the primary way small firms choose software.", "Опрос ассоциации это подтверждает."),
            ("Сделка затягивается из-за проверки конфликта интересов и безопасности.", "Каждая неделя согласований отодвигает первую оплату.", 2, "not_supported", "Most firms under fifteen lawyers have no formal vendor review.", "У малых фирм формальной проверки поставщиков нет."),
        ],
        "test": ("Выступления в местных ассоциациях юристов и рекомендации", "Разбор 20 обращений бесплатно, дальше 79 долларов за место в месяц", "3 фирмы подключили больше одного юриста"),
        "upsell": "Компаниям, которые уже продают юристам: справочные системы, учёт времени, электронная подпись.",
        "advice": ("postpone", "До 7 тысяч долларов, основная часть на личные встречи", "Договориться о выступлении в одной ассоциации юристов", "После 30 разборов нет ни одной оплаты"),
        "trust": "medium",
        "human": [],
    },
    "roomloop": {
        "levels": [3, 4, 4, 3, 2, 3],
        "anchor": "Hostgrid: подписка за объект, оценка $650 млн по публикации в прессе.",
        "objections": [
            ("Работа держится на API площадок бронирования, доступ дают только партнёрам и могут отозвать.", "Без доступа продукт не работает вовсе, а решение принимает площадка.", 5, "supported", "API access is granted to approved connectivity partners only.", "Условия партнёрской программы это подтверждают."),
            ("Рынок занят десятками зрелых менеджеров каналов.", "Новому игроку нечем отличиться, кроме цены.", 3, "supported", "More than forty channel managers are listed in the partner directory.", "Каталог партнёров площадки подтверждает число."),
            ("Управляющие меняют инструмент только в межсезонье.", "Тест в сезон покажет нулевой интерес независимо от продукта.", 2, "source_unavailable", "", "Источник недоступен из-за ограничения по региону."),
        ],
        "test": ("Группы управляющих в социальных сетях", "Первый объект бесплатно на месяц, дальше 12 долларов за объект", "10 управляющих подключили больше трёх объектов"),
        "upsell": "Компаниям с базой владельцев жилья: уборка, страхование объектов, умные замки.",
        "advice": ("postpone", "До 5 тысяч долларов после получения доступа к API", "Подать заявку в партнёрскую программу двух площадок", "Доступ к API не выдан за шесть недель"),
        "trust": "medium",
        "human": ["Узнать срок рассмотрения заявки на партнёрский доступ к API"],
    },
    "lumenqa": {
        "levels": [3, 3, 4, 3, 4, 3],
        "anchor": "Testharbor: плата за прогоны, оценка $1,1 млрд по раунду 2025 года.",
        "objections": [
            ("Бесплатные открытые инструменты закрывают базовые сценарии.", "Команда сначала попробует бесплатное и до платного не дойдёт.", 3, "supported", "The open-source runner covers most smoke tests out of the box.", "Документация открытого инструмента это подтверждает."),
            ("Ложные срабатывания подрывают доверие команды за первые недели.", "После нескольких ложных тревог прогоны перестают смотреть.", 4, "not_supported", "Flaky results were reported in under 4% of runs.", "Источник приводит низкую долю ложных срабатываний."),
            ("Покупает руководитель разработки, а пользуется тестировщик.", "Два человека в сделке удлиняют путь до оплаты.", 2, "failed", "", ""),
        ],
        "test": ("Сообщества мобильных разработчиков и сообщения руководителям", "100 прогонов бесплатно, дальше 0,4 доллара за прогон", "5 команд израсходовали бесплатные прогоны и пополнили счёт"),
        "upsell": "Компаниям с базой команд разработки: система сборки, мониторинг ошибок, аутсорс тестирования.",
        "advice": ("postpone", "До 8 тысяч долларов: устройства для прогонов стоят дороже разработки", "Сделать прогон для трёх знакомых команд", "Ни одна команда не пополнила счёт после бесплатных прогонов"),
        "trust": "medium",
        "human": [],
    },
    "dockhand": {
        "levels": [3, 2, 2, 4, 3, 3],
        "anchor": "Cargoledger: подписка для экспедиторов, оценка $1,4 млрд по раунду 2024 года.",
        "objections": [
            ("Экспедиторы покупают через закупку с проверкой безопасности, сделка длится кварталами.", "Первая оплата не укладывается в три месяца.", 4, "supported", "Typical procurement cycles for logistics software run four to six months.", "Отраслевой обзор называет тот же срок."),
            ("Ошибка в таможенном документе ведёт к штрафу, клиент потребует ответственности.", "Ответственность за ошибку программы ляжет на нас или сорвёт сделку.", 4, "supported", "The broker remains liable for the accuracy of every declaration.", "Правила таможни возлагают ответственность на брокера."),
            ("Форматы документов различаются по странам, один продукт не покрывает рынок.", "Каждая новая страна требует отдельной разработки.", 3, "not_supported", "The same bill of lading fields are used across major trade lanes.", "Основные поля документов совпадают."),
        ],
        "test": ("Отраслевые выставки и личные рекомендации", "Разбор 100 документов бесплатно, дальше 0,8 доллара за документ", "2 брокера подписали договор после пилота"),
        "upsell": "Компаниям с базой перевозчиков и брокеров: биржа грузов, страхование грузов, отслеживание контейнеров.",
        "advice": ("postpone", "До 10 тысяч долларов, из них половина на юриста", "Найти одного брокера, готового на пилот с оговоркой об ответственности", "Пилот не начался за два месяца"),
        "trust": "high",
        "human": ["Уточнить у брокера, кто отвечает за ошибку программы"],
    },
    "benchmate": {
        "levels": [3, 2, 2, 2, 3, 2],
        "anchor": "Labvault: подписка для лабораторий, размер подтверждён одной публикацией.",
        "objections": [
            ("Лаборатории платят из грантов раз в год, первая оплата придёт не раньше нового бюджетного цикла.", "Даже согласный клиент заплатит через полгода.", 5, "supported", "Purchases above the threshold must be included in the next annual budget.", "Правила закупок университета это подтверждают."),
            ("Лаборатории ведут учёт в таблицах и не видят причины платить.", "Бесплатная привычка сильнее платного удобства.", 3, "supported", "Spreadsheets remain the most common inventory tool in academic labs.", "Опрос лабораторий подтверждает."),
            ("Поставщики реагентов дают свой учёт бесплатно.", "Бесплатный учёт от поставщика закрывает ту же задачу.", 3, "contradicts", "The vendor portal tracks only orders placed with that vendor.", "Портал поставщика ведёт только свои заказы, а не весь склад."),
        ],
        "test": ("Конференции и рассылки для руководителей лабораторий", "Бесплатный перенос учёта из таблиц, дальше 1 200 долларов в год", "2 лаборатории оплатили годовой счёт"),
        "upsell": "Поставщикам реагентов и оборудования как сервис для своих клиентов.",
        "advice": ("postpone", "До 3 тысяч долларов на проверку спроса без разработки", "Показать макет пяти руководителям лабораторий", "Никто из пяти не готов платить в этом бюджетном году"),
        "trust": "medium",
        "human": [],
    },
    "stockroom": {
        "levels": [1, 2, 2, 4, 2, 2],
        "anchor": "Wholesail: комиссия с оптовых заказов, оценка $3,4 млрд по раунду 2023 года.",
        "objections": [
            ("Двусторонняя площадка пуста без обеих сторон, за три месяца ликвидность не набрать.", "Без покупателей не придут бренды, без брендов не придут покупатели.", 5, "supported", "It took the marketplace two years to reach repeat-order liquidity.", "Интервью основателя называет срок в два года."),
            ("Площадка проводит платежи между сторонами, это близко к хранению чужих денег.", "Тогда модель нарушает жёсткий критерий собственника.", 4, "not_supported", "Funds are held and settled by the payment partner.", "По источнику расчёты ведёт платёжный партнёр."),
            ("Бренды уходят в прямые продажи после первой сделки.", "Комиссия с повторных заказов не возникает.", 3, "supported", "A third of brands moved repeat orders off-platform.", "Исследование называет долю в треть."),
        ],
        "test": ("Прямые продажи брендам на отраслевых ярмарках", "Первые три заказа без комиссии", "20 повторных заказов за три месяца"),
        "upsell": "Компаниям, у которых уже есть одна из сторон: платёжный сервис для магазинов, логистика для брендов.",
        "advice": ("postpone", "Не вкладывать до появления готовой базы одной из сторон", "Проверить, есть ли в холдинге компания с базой магазинов", "Нет доступа к готовой базе покупателей"),
        "trust": "medium",
        "human": ["Решить, есть ли у холдинга готовая база магазинов или брендов"],
    },
}  # fmt: skip

MEMO = """Первой запускать **Tallybook**: тест собирается за месяц, покупателя видно, оплата картой. Вторым идёт **Chartwell Notes**, но до пилота нужно соглашение о защите данных.

**Fieldnote** выглядит сильно, однако карточка стоит на слабых данных: главное возражение не удалось проверить. Сначала пять разговоров с владельцами, потом решение.

Отложить **Stockroom** и **Benchmate**. У первой нет ликвидности без готовой базы одной из сторон, у второй первая оплата упирается в годовой бюджетный цикл."""

INDUSTRIES = {
    "B2B": (["sales teams", "finance teams", "HR departments", "IT helpdesks"], "Отделы малого и среднего бизнеса"),
    "Consumer": (["families", "renters", "pet owners", "students"], "Частные пользователи"),
    "Healthcare": (["dental clinics", "home care agencies", "physiotherapists"], "Небольшие клиники"),
    "Fintech": (["small lenders", "accounting firms", "treasury teams"], "Финансовые отделы компаний"),
    "Industrials": (["machine shops", "logistics operators", "field crews"], "Производственные компании"),
    "Real Estate and Construction": (["property managers", "general contractors"], "Управляющие недвижимостью"),
    "Education": (["tutoring centers", "universities"], "Учебные центры"),
    "Government": (["city agencies", "public schools"], "Муниципальные службы"),
}  # fmt: skip
PRODUCTS = [
    "AI assistant", "Workflow automation", "Analytics platform", "Billing software",
    "Scheduling assistant", "Compliance toolkit", "Voice agent", "Procurement marketplace",
    "Data pipeline", "Customer support desk",
]  # fmt: skip
STEMS = ["Nor", "Vel", "Kin", "Sol", "Tar", "Mer", "Ost", "Bri", "Cal", "Dex", "Fen", "Gal", "Hal", "Ivo", "Jun", "Kor", "Lex", "Mav", "Nim", "Orb", "Pax", "Rho", "Syl", "Tek", "Ulm", "Vex", "Wyn", "Zen"]  # fmt: skip
ENDINGS = ["ia", "ly", "io", "ify", "base", "desk", "flow", "grid", "path", "works", "loop", "stack", "mint", "port", "wise"]  # fmt: skip

# критерий → (причина отказа по описанию, узел, который лес проверит на контрольной выборке)
REJECTIONS = {
    "money_risk": [
        ("Выдаёт займы клиентам от своего имени", "money_risk.lends", "yes"),
        ("Продаёт страховые полисы и сам несёт страховой риск", "money_risk.insures", "yes"),
        ("Хранит деньги клиентов на своих счетах", "money_risk.holds_funds", "yes"),
    ],
    "online": [
        ("Продаёт физическое устройство, поставка не онлайн", "online.fully_online", "no"),
        ("Для работы нужна медицинская лицензия", "online.own_license", "yes"),
        ("Услуга требует выезда к клиенту", "online.fully_online", "no"),
    ],
    "recurring": [
        ("Разовая продажа без повторных платежей", "recurring.commission", "no"),
        ("Доход от разовых проектов под заказ", "recurring.commission", "no"),
    ],
    "not_trading_gov": [
        ("Доход от собственной торговли на бирже", "not_trading_gov.trading", "yes"),
        ("Услуга оказывается по государственному заказу", "not_trading_gov.gov_service", "yes"),
    ],
}
REJECTION_WEIGHTS = {"money_risk": 38, "online": 44, "recurring": 23, "not_trading_gov": 12}
QUEUE_REASONS = {
    2: "Долгая сделка с крупным заказчиком.",
    3: "Нужна интеграция с системами клиента.",
    4: "Понятный покупатель и короткая сделка, но отрасль уже представлена тремя моделями.",
    5: "Самообслуживание и оплата картой, но отрасль уже представлена тремя моделями.",
}


def company(slug: str, name: str, one_liner: str, industry: str) -> Company:
    return Company(
        slug=slug,
        name=name,
        one_liner=one_liner,
        description=f"{one_liner}. Founded by a small team, sells online to customers in North America.",
        industry=industry,
        subindustry=industry,
        tags=["SaaS", "AI"],
        batch=rng.choice(["Summer 2026", "Fall 2026", "Winter 2025", "Spring 2024"]),
        team_size=rng.choice([2, 3, 4, 6, 9, 14, None]),
        website=f"https://{slug}.example.com",
        yc_url=f"https://catalog.example.org/companies/{slug}",
    )


def generic_companies(count: int) -> list[Company]:
    names = [stem + ending for stem in STEMS for ending in ENDINGS]
    rng.shuffle(names)
    companies = []
    for name in names[:count]:
        industry = rng.choices(list(INDUSTRIES), weights=[50, 14, 11, 11, 8, 3, 2, 1])[0]
        buyers, _ = INDUSTRIES[industry]
        one_liner = f"{rng.choice(PRODUCTS)} for {rng.choice(buyers)}"
        companies.append(company(name.lower(), name, one_liner, industry))
    return companies


def generic_model(industry: str) -> BusinessModel:
    return BusinessModel(
        payer=INDUSTRIES[industry][1],
        pays_for="Доступ к сервису",
        frequency="Ежемесячно",
        revenue_type="subscription",
    )


def evidence_for(slug: str, name: str) -> list[Evidence]:
    pages = [
        ("E1", f"https://{slug}.example.com/", f"{name}: product overview"),
        ("E2", f"https://{slug}.example.com/pricing", f"{name}: pricing"),
        ("E3", f"https://{slug}.example.com/terms", f"{name}: terms of service"),
        ("E4", f"https://press.example.org/funding/{slug}", "Funding round coverage"),
        ("E5", f"https://registry.example.net/licenses/{slug}", "Regulatory register entry"),
        ("E6", f"https://reviews.example.org/{slug}", "Customer reviews"),
    ]
    return [
        Evidence(
            id=evidence_id,
            url=url,
            title=title,
            published=None if evidence_id == "E6" else f"2026-{rng.randint(1, 10):02d}-{rng.randint(1, 28):02d}",
            accessed=TODAY,
            sha256=hashlib.sha256(url.encode()).hexdigest(),
        )
        for evidence_id, url, title in pages
    ]  # fmt: skip


def decide(
    node: str, label: str, truth: str, passing: str, source: Evidence
) -> tuple[Decision, str]:
    """Возвращает решение по узлу и ответ, с которым дальше идёт обход дерева.

    Особые случаи: blank — все голоса «неизвестно», arbiter — голоса 4 против 2 (меньше порога)
    и решает арбитр, unresolved — голоса 4 против 2 и арбитр не решил.
    """
    opposite = {"yes": "no", "no": "yes"}
    seats = len(VOTERS)
    if truth == "blank":
        answers, answer, decided_by = ["unknown"] * seats, "unknown", "vote"
    elif truth in ("arbiter", "unresolved"):
        answers = rng.sample(
            [passing] * (QUORUM - 1) + [opposite[passing]] * (seats - QUORUM + 1), seats
        )
        answer = passing if truth == "arbiter" else "unknown"
        decided_by = truth
    else:
        dissent = [opposite[truth]] * (seats - QUORUM) if rng.random() < 0.22 else []
        answers = rng.sample([truth] * (seats - len(dissent)) + dissent, seats)
        answer, decided_by = truth, "vote"
    counted = answer if answer in answers else Counter(answers).most_common(1)[0][0]
    votes = [
        Vote(
            voter=voter,
            answer=vote,
            quote=QUOTES[node] if vote == counted and vote != "unknown" else "",
            evidence_id=source.id if vote == counted and vote != "unknown" else "",
        )
        for voter, vote in zip(VOTERS, answers)
    ]
    decision = Decision(
        question_id=node,
        question=label,
        votes=votes,
        answer=answer,
        agreement=answers.count(counted) / seats,
        decided_by=decided_by,
    )
    return decision, answer


def passport_for(tree_id: str, decision: Decision, source: Evidence) -> Passport:
    spoken = {"yes": "да", "no": "нет", "unknown": "неизвестно"}[decision.answer]
    if decision.answer == "unknown":
        method, confidence, quote = "needs_human", "low", None
    elif decision.decided_by == "arbiter":
        method, confidence, quote = "model_judgment", "low", None
    else:
        method, quote = "primary_source", QUOTES[decision.question_id.split(".")[1]]
        confidence = "high" if decision.agreement == 1 else "medium"
    return Passport(
        id=f"gate.{decision.question_id}",
        claim=f"{decision.question}: {spoken}",
        origin="gate",
        method=method,
        confidence=confidence,
        source_url=source.url if quote else None,
        quote=quote,
        source_date=source.published if quote else None,
        accessed=TODAY if quote else None,
        note="" if quote else "Голоса разошлись или источников не хватило.",
    )


def gate_for(slug: str, name: str, twists: dict[str, str]) -> Gate:
    evidence = evidence_for(slug, name)
    by_id = {item.id: item for item in evidence}
    decisions, passports, trees = [], [], []
    for tree_id, title, mode, nodes in TREES:
        answers = {}
        for node, label, passing, evidence_id in nodes:
            question = f"{tree_id}.{node}"
            default = "no" if node == "commission" else passing
            decision, answers[node] = decide(
                node, label, twists.get(question, default), passing, by_id[evidence_id]
            )
            decision.question_id = question
            passport = passport_for(tree_id, decision, by_id[evidence_id])
            decision.passport_id = passport.id
            decisions.append(decision)
            passports.append(passport)
        outcome, path = walk(mode, nodes, answers)
        reason = (
            TREE_REASONS.get((slug, tree_id))
            or {
                "pass": "Ответы на пройденных узлах подтверждают критерий.",
                "fail": FAIL_REASONS.get(path[-1], ""),
                "unknown": "Источников не хватило, вопрос передан человеку.",
            }[outcome]
        )
        trees.append(
            TreeResult(
                tree_id=tree_id,
                title=title,
                outcome=outcome,
                path=[f"{tree_id}.{node}" for node in path],
                reason=reason,
            )
        )
    outcomes = {tree.outcome for tree in trees}
    overall = "fail" if "fail" in outcomes else "unknown" if "unknown" in outcomes else "pass"
    return Gate(
        slug=slug,
        outcome=overall,
        trees=trees,
        decisions=decisions,
        evidence=evidence,
        passports=passports,
        forest_version=FOREST_VERSION,
    )


def walk(mode: str, nodes: list[tuple], answers: dict[str, str]) -> tuple[str, list[str]]:
    path = []
    for node, _, passing, _ in nodes:
        path.append(node)
        if answers[node] == "unknown":
            return "unknown", path
        if mode == "any" and answers[node] == passing:
            return "pass", path
        if mode == "all" and answers[node] != passing:
            return "fail", path
    return ("pass" if mode == "all" else "fail"), path


def objections_for(slug: str, rows: list[tuple]) -> tuple[list[Objection], list[Passport]]:
    objections, passports = [], []
    for number, (text, reasoning, strength, verdict, quote, note) in enumerate(rows, start=1):
        sent = verdict is not None
        source = f"https://press.example.org/analysis/{slug}-{number}" if quote or sent else None
        source_date = f"2026-{rng.randint(2, 10):02d}-{rng.randint(1, 28):02d}" if quote else None
        confirmed = verdict in ("supported", "not_supported", "contradicts")
        passport = Passport(
            id=f"objection.O{number}",
            claim=text,
            origin="critic",
            method="primary_source" if confirmed else "model_judgment",
            confidence="high" if verdict == "supported" else "medium" if confirmed else "low",
            source_url=source,
            quote=quote or None,
            source_date=source_date,
            accessed=TODAY if source else None,
            note=note,
        )
        objections.append(
            Objection(
                id=f"O{number}",
                text=text,
                reasoning=reasoning,
                strength=strength,
                source_url=source,
                quote=quote or None,
                source_date=source_date,
                sent_to_verifier=sent,
                verdict=None if verdict == "failed" else verdict,
                verifier_quote=quote if confirmed else None,
                verifier_note=note,
                passport_id=passport.id,
            )
        )
        passports.append(passport)
    return objections, passports


def card_for(slug: str, gate: Gate) -> Card:
    name, one_liner, _, payer, pays_for, frequency, revenue_type = SELECTED[slug]
    spec = CARDS[slug]
    rubrics = [
        Rubric(id=rubric_id, title=title, weight=weight, level=level, why=whys[(level - 1) // 2])
        for (rubric_id, title, weight, whys), level in zip(RUBRICS, spec["levels"])
    ]
    objections, objection_passports = objections_for(slug, spec["objections"])
    passports = gate.passports + objection_passports
    verdict, budget, first_step, stop_signal = spec["advice"]
    confirmed = [o for o in objections if o.verdict == "supported"] or objections
    return Card(
        slug=slug,
        name=name,
        one_liner=one_liner,
        website=f"https://{slug}.example.com",
        yc_url=f"https://catalog.example.org/companies/{slug}",
        business_model=BusinessModel(
            payer=payer, pays_for=pays_for, frequency=frequency, revenue_type=revenue_type
        ),
        anchor=spec["anchor"],
        score=sum(rubric.weight * (rubric.level - 1) / 4 for rubric in rubrics),
        rank=0,
        rubrics=rubrics,
        objections=objections,
        test_sketch=TestSketch(
            channel=spec["test"][0], offer=spec["test"][1], success_sign=spec["test"][2]
        ),
        upsell=spec["upsell"],
        needs_human=spec["human"],
        passports=passports,
        trust=Trust(
            by_method=Counter(passport.method for passport in passports),
            by_confidence=Counter(passport.confidence for passport in passports),
            level=spec["trust"],
        ),
        advice=Advice(
            verdict=verdict,
            test_budget=budget,
            first_step=first_step,
            main_risk=max(confirmed, key=lambda objection: objection.strength).text,
            stop_signal=stop_signal,
            flagged_numbers=spec.get("flagged", []),
        ),
    )


def isolation_for(card: Card) -> Isolation:
    def fingerprint(*parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    checked = [objection for objection in card.objections if objection.sent_to_verifier]
    return Isolation(
        slug=card.slug,
        critic=AgentCall(
            role="critic",
            model="claude-opus-5-5",
            input_sha=fingerprint(card.slug, "critic"),
            inputs=[
                "Схема модели: кто платит, за что, как часто",
                "Описание компании из каталога",
                "Результаты четырёх собственных поисковых запросов",
            ],
        ),
        verifier=[
            AgentCall(
                role="verifier",
                model="openai/gpt-6.2-sol",
                input_sha=fingerprint(card.slug, objection.id),
                inputs=[
                    f"Текст утверждения {objection.id}",
                    "Адрес источника",
                    "Текст страницы, скачанный заново",
                ],
            )
            for objection in checked
        ],
        leaked=[],
    )


def build() -> Run:
    companies = {slug: company(slug, spec[0], spec[1], spec[2]) for slug, spec in SELECTED.items()}
    prescreens = [
        Prescreen(
            slug=slug,
            business_model=BusinessModel(
                payer=spec[3], pays_for=spec[4], frequency=spec[5], revenue_type=spec[6]
            ),
            violations=[],
            speed=rng.choice([4, 5]),
            speed_reason="Покупателя видно, первая оплата возможна в пределах трёх месяцев.",
            status="selected",
        )
        for slug, spec in SELECTED.items()
    ]
    gates = [gate_for(slug, spec[0], TWISTS.get(slug, {})) for slug, spec in SELECTED.items()]

    others = generic_companies(185)
    companies |= {item.slug: item for item in others}
    control_twists = {}
    for item in others[:117]:
        criterion = rng.choices(list(REJECTIONS), weights=list(REJECTION_WEIGHTS.values()))[0]
        reason, node, answer = rng.choice(REJECTIONS[criterion])
        control_twists[item.slug] = {node: answer}
        if criterion == "recurring":
            control_twists[item.slug]["recurring.subscription"] = "no"
        prescreens.append(
            Prescreen(
                slug=item.slug,
                business_model=generic_model(item.industry),
                violations=[Violation(criterion=criterion, reason=reason)],
                speed=1,
                speed_reason="Не оценивалась: модель отсеяна по описанию.",
                status="rejected",
            )
        )
    for item in others[117:184]:
        speed = rng.choices([2, 3, 4, 5], weights=[20, 30, 12, 5])[0]
        prescreens.append(
            Prescreen(
                slug=item.slug,
                business_model=generic_model(item.industry),
                violations=[],
                speed=speed,
                speed_reason=QUEUE_REASONS[speed],
                status="queued",
            )
        )
    lost = others[184]
    prescreens.append(
        Prescreen(
            slug=lost.slug,
            business_model=generic_model(lost.industry),
            violations=[],
            speed=1,
            speed_reason="Шаг не выполнен.",
            status="failed",
        )
    )

    control = [item.slug for item in rng.sample(others[:117], 10)]
    spared = control[3]
    for slug in control:
        twists = {} if slug == spared else control_twists[slug]
        gates.append(gate_for(slug, companies[slug].name, twists))

    gate_by_slug = {gate.slug: gate for gate in gates}
    cards = [card_for(slug, gate_by_slug[slug]) for slug in CARDS]
    for rank, card in enumerate(sorted(cards, key=lambda card: -card.score), start=1):
        card.rank = rank

    deep = [gate_by_slug[slug] for slug in SELECTED]
    return Run(
        id="fixture-2026-11-26",
        started="2026-11-26T09:12:40",
        finished="2026-11-26T09:41:05",
        profile="fixture",
        voters=VOTERS,
        quorum=QUORUM,
        spent={"anthropic": 2.52, "openrouter": 0.48},
        config={
            path.stem: yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in sorted((ROOT / "config").glob("*.yaml"))
        },
        prompts={
            path.stem: path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "prompts").glob("*.md"))
        },
        funnel=Funnel(
            sourced=len(companies),
            prescreen_rejected=117,
            queued=67,
            deep_checked=len(deep),
            gate_passed=sum(gate.outcome == "pass" for gate in deep),
            gate_failed=sum(gate.outcome == "fail" for gate in deep),
            gate_unknown=sum(gate.outcome == "unknown" for gate in deep),
            carded=len(cards),
            unverified=1,
        ),
        companies=companies,
        prescreens=prescreens,
        gates=gates,
        cards=cards,
        memo=MEMO,
        control=ControlSample(slugs=control, wrongly_rejected=[spared]),
        costs=[
            Cost(provider="anthropic", role="prescreen", model="claude-haiku-5-5", calls=200, cached=0, input_tokens=131400, output_tokens=58200, usd=0.04),
            Cost(provider="anthropic", role="planner", model="claude-haiku-5-5", calls=25, cached=0, input_tokens=21300, output_tokens=6100, usd=0.01),
            Cost(provider="openrouter", role="voter", model="google/gemma-4-26b-a4b-it", calls=25, cached=0, input_tokens=148200, output_tokens=17400, usd=0.03),
            Cost(provider="openrouter", role="voter", model="meta-llama/llama-4-maverick", calls=25, cached=0, input_tokens=148200, output_tokens=16900, usd=0.06),
            Cost(provider="openrouter", role="voter", model="deepseek/deepseek-v4.1-flash", calls=25, cached=0, input_tokens=148200, output_tokens=18800, usd=0.03),
            Cost(provider="openrouter", role="voter", model="mistralai/mistral-small-2603", calls=25, cached=0, input_tokens=148200, output_tokens=18300, usd=0.03),
            Cost(provider="openrouter", role="voter", model="openai/gpt-6-luna", calls=25, cached=0, input_tokens=148200, output_tokens=17100, usd=0.02),
            Cost(provider="anthropic", role="voter", model="claude-sonnet-5-5", calls=25, cached=0, input_tokens=151900, output_tokens=24800, usd=0.55),
            Cost(provider="anthropic", role="arbiter", model="claude-opus-5-5", calls=4, cached=0, input_tokens=22600, output_tokens=3900, usd=0.17),
            Cost(provider="anthropic", role="critic", model="claude-opus-5-5", calls=20, cached=2, input_tokens=118700, output_tokens=41200, usd=1.3),
            Cost(provider="openrouter", role="verifier", model="openai/gpt-6.2-sol", calls=26, cached=0, input_tokens=109300, output_tokens=14700, usd=0.37),
            Cost(provider="anthropic", role="card", model="claude-sonnet-5-5", calls=9, cached=0, input_tokens=61800, output_tokens=15300, usd=0.28),
            Cost(provider="anthropic", role="advisor", model="claude-sonnet-5-5", calls=10, cached=0, input_tokens=38400, output_tokens=9700, usd=0.17),
        ],
        validators=ValidatorStats(
            schema_retries=7,
            schema_failures=2,
            quotes_checked=214,
            quotes_dropped=9,
            advice_numbers_flagged=1,
            cards_rejected=0,
        ),
        isolation=[isolation_for(card) for card in cards],
        failures=[
            Failure(slug="paygrid", stage="critic", error="Ответ не по схеме и после повтора: нет списка возражений."),
            Failure(slug=lost.slug, stage="prescreen", error="Провайдер не ответил за 60 секунд, запасной маршрут тоже."),
        ],
        outage_drill=OutageDrill(
            role="critic",
            failed_route="anthropic / claude-opus-5-5",
            error="APIConnectionError: соединение намеренно разорвано для учения.",
            served_by="openrouter / anthropic/claude-opus-5.5",
            seconds=2.4,
        ),
        golden=GoldenScore(
            labelled=85,
            agreed=79,
            disagreements=[
                "Roomloop, «Её размер от $300 млн подтверждён»: человек ответил «не знаю», лес «да».",
                "Sablebase, «Нужна своя лицензия до первого клиента»: человек ответил «да», лес не решил.",
                "Dockhand, «Продаётся и оказывается полностью онлайн»: человек ответил «нет», лес «да».",
            ],
        ),
    )  # fmt: skip


if __name__ == "__main__":
    target = Path(__file__).with_name("run.json")
    target.write_text(build().model_dump_json(), encoding="utf-8")
    print(f"{target} записан")
