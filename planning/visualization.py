"""
Модуль для визуализации календарного плана в виде диаграммы Ганта
"""

from PIL import Image, ImageDraw, ImageFont
from datetime import timedelta, datetime
import random


def generate_gantt_chart(calendar_plan):
    """
    Генерирует изображение диаграммы Ганта для календарного плана.
    """
    tasks = calendar_plan['tasks']

    # Добавим диагностическую печать
    print(f"Попытка отобразить {len(tasks)} задач")

    if not tasks:
        image = Image.new('RGB', (400, 200), 'white')
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype('arial.ttf', 12)
        except IOError:
            font = ImageFont.load_default()
        draw.text((10, 10), "Нет задач для отображения", fill="black", font=font)
        return image

    # Определяем временные границы
    start_date = min(task['start_date'] for task in tasks)
    end_date = max(task['end_date'] for task in tasks)
    project_duration = (end_date - start_date).days + 1

    # Настройки изображения
    task_height = 30
    day_width = 30
    margin_left = 250
    margin_top = 60
    legend_height = 50

    # Создаем изображение
    image_width = margin_left + day_width * project_duration
    image_height = margin_top + task_height * len(tasks) + legend_height

    image = Image.new('RGB', (image_width, image_height), 'white')
    draw = ImageDraw.Draw(image)

    # Пытаемся загрузить шрифт
    try:
        title_font = ImageFont.truetype('arial.ttf', 16)
        font = ImageFont.truetype('arial.ttf', 12)
        small_font = ImageFont.truetype('arial.ttf', 10)
    except IOError:
        title_font = ImageFont.load_default()
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # Добавляем заголовок
    title = "Диаграмма Ганта проекта"
    draw.text((image_width // 2 - len(title) * 4, 10), title, fill='black', font=title_font)

    # Рисуем шкалу времени
    current_date = start_date
    for day in range(project_duration):
        x = margin_left + (day * day_width)
        date_str = current_date.strftime('%d.%m')
        draw.text((x, margin_top - 20), date_str, fill='black', font=font)
        current_date += timedelta(days=1)

        # Вертикальные линии сетки
        draw.line([(x, margin_top - 5), (x, image_height - legend_height)], fill='lightgray')

        # Выделяем выходные
        if current_date.weekday() >= 5:
            draw.rectangle(
                [(x, margin_top), (x + day_width, image_height - legend_height)],
                fill='#f0f0f0', outline=None
            )

    # Рисуем задачи
    for i, task in enumerate(tasks):
        y = margin_top + i * task_height

        # Рисуем название задачи
        task_name = task['name']
        if len(task_name) > 25:
            task_name = task_name[:22] + "..."
        draw.text((10, y + 10), task_name, fill='black', font=font)

        # Рисуем исполнителя
        employee_name = task.get('employee', 'Не назначен')
        if len(employee_name) > 15:
            employee_name = employee_name[:12] + "..."
        draw.text((margin_left - 150, y + 10), employee_name, fill='black', font=font)

        # Вычисляем координаты для задачи
        days_from_start = max(0, (task['start_date'] - start_date).days)
        task_duration = max(1, (task['end_date'] - task['start_date']).days + 1)

        left = margin_left + days_from_start * day_width
        top = y + 5
        right = left + task_duration * day_width
        bottom = top + task_height - 10

        # Безопасная проверка для прямоугольника
        if right <= left:
            right = left + day_width

        # Цвет для задачи
        color = 'red' if task.get('is_critical', False) else 'blue'

        # Рисуем полосу задачи
        draw.rectangle([left, top, right, bottom], fill=color, outline='black')

        # Добавляем текст с длительностью
        duration_text = f"{task_duration}д."
        text_width = len(duration_text) * 6

        if right - left > text_width + 4:
            text_x = left + (right - left - text_width) // 2
            draw.text((text_x, top + 5), duration_text, fill='white', font=small_font)

    # Рисуем легенду
    legend_y = image_height - legend_height + 10

    # Критическая задача
    draw.rectangle([margin_left, legend_y, margin_left + 20, legend_y + 20], fill='red', outline='black')
    draw.text((margin_left + 25, legend_y + 5), "Критическая задача", fill='black', font=font)

    # Обычная задача
    draw.rectangle([margin_left + 200, legend_y, margin_left + 220, legend_y + 20], fill='blue', outline='black')
    draw.text((margin_left + 225, legend_y + 5), "Обычная задача", fill='black', font=font)

    return image

def draw_time_scale(draw, start_date, duration, margin_left, margin_top, day_width, image_height, font):
    """
    Рисует шкалу времени и сетку для диаграммы Ганта.

    Args:
        draw: Объект ImageDraw
        start_date: Начальная дата проекта
        duration: Продолжительность проекта в днях
        margin_left: Отступ слева
        margin_top: Отступ сверху
        day_width: Ширина одного дня
        image_height: Высота изображения
        font: Шрифт для текста
    """
    # Рисуем горизонтальные линии сетки
    for y in range(margin_top, image_height, 30):
        draw.line([(0, y), (margin_left + duration * day_width, y)], fill='lightgray')

    # Рисуем вертикальные линии сетки и метки дат
    for i in range(duration + 1):
        date = start_date + timedelta(days=i)
        x = margin_left + i * day_width

        # Вертикальная линия
        draw.line([(x, margin_top - 20), (x, image_height)], fill='lightgray')

        # Метка даты
        date_text = date.strftime('%d.%m')
        draw.text((x - 15, margin_top - 20), date_text, fill='black', font=font)

        # Выделяем выходные дни (суббота и воскресенье)
        if date.weekday() >= 5:  # 5 - суббота, 6 - воскресенье
            draw.rectangle(
                [(x, margin_top), (x + day_width, image_height)],
                fill='#f0f0f0',
                outline=None
            )

    # Добавляем метки для заголовков столбцов
    draw.text((10, margin_top - 20), "Задача", fill='black', font=font)
    draw.text((margin_left - 100, margin_top - 20), "Исполнитель", fill='black', font=font)


def draw_task(draw, task, index, start_date, margin_left, margin_top, day_width, task_height, colors, font, small_font):
    """
    Рисует задачу на диаграмме Ганта.
    """
    y = margin_top + index * task_height + 5

    # Рисуем название задачи
    task_name = task['name']
    if len(task_name) > 30:
        task_name = task_name[:27] + "..."
    draw.text((10, y + 5), task_name, fill='black', font=font)

    # Рисуем имя исполнителя
    employee_name = task['employee']
    if len(employee_name) > 15:
        employee_name = employee_name[:12] + "..."
    draw.text((margin_left - 100, y + 5), employee_name, fill='black', font=font)

    # Координаты задачи
    days_from_start = (task['start_date'] - start_date).days
    task_duration = (task['end_date'] - task['start_date']).days + 1

    # Убедимся, что продолжительность задачи всегда положительная
    if task_duration <= 0:
        task_duration = 1  # Минимальная продолжительность - 1 день

    left = margin_left + days_from_start * day_width
    top = y
    right = left + task_duration * day_width  # Теперь right всегда больше left
    bottom = top + task_height - 10

    # Проверяем, что координаты правильные
    if right <= left:
        right = left + day_width  # Обеспечиваем минимальную ширину 1 день

    # Определяем цвет задачи
    if task['id'] in colors:
        color = colors[task['id']]
    else:
        # Если задача новая и для неё нет цвета, используем цвет по умолчанию
        color = (255, 170, 170) if task.get('is_critical', False) else (170, 170, 255)
        colors[task['id']] = color  # Добавляем цвет в словарь

    # Рисуем прямоугольник задачи
    draw.rectangle([left, top, right, bottom], fill=color, outline='black')

    # Добавляем штриховку для критических задач
    if task.get('is_critical', False):
        draw_hatching(draw, left, top, right, bottom)

    # Информация о длительности
    duration_text = f"{task_duration}д."
    try:
        text_width = draw.textlength(duration_text, font=small_font)
    except:
        # Для старых версий PIL
        text_width = len(duration_text) * 6  # примерная ширина текста

    # Проверяем, достаточно ли места для текста
    if right - left > text_width + 10:
        draw.text((left + 5, top + 5), duration_text, fill='black', font=small_font)

def draw_hatching(draw, left, top, right, bottom):
    """
    Рисует штриховку для критических задач.

    Args:
        draw: Объект ImageDraw
        left, top, right, bottom: Координаты прямоугольника задачи
    """
    # Штриховка для критических задач (диагональные линии)
    for i in range(left, right, 5):
        draw.line([(i, top), (i + 10, bottom)], fill='black', width=1)


def draw_legend(draw, image_width, image_height, legend_height, font):
    """
    Рисует легенду диаграммы.

    Args:
        draw: Объект ImageDraw
        image_width: Ширина изображения
        image_height: Высота изображения
        legend_height: Высота легенды
        font: Шрифт для текста
    """
    legend_top = image_height - legend_height

    # Фон легенды
    draw.rectangle([(0, legend_top), (image_width, image_height)], fill='#f8f8f8', outline='lightgray')

    # Заголовок легенды
    draw.text((10, legend_top + 5), "Легенда:", fill='black', font=font)

    # Элементы легенды

    # Критический путь
    sample_left = 100
    sample_top = legend_top + 20
    sample_right = sample_left + 40
    sample_bottom = sample_top + 20

    # Образец критической задачи
    draw.rectangle([sample_left, sample_top, sample_right, sample_bottom], fill='#ffaaaa', outline='black')
    draw_hatching(draw, sample_left, sample_top, sample_right, sample_bottom)
    draw.text((sample_right + 10, sample_top + 5), "Критическая задача", fill='black', font=font)

    # Образец обычной задачи
    sample_left = 300
    draw.rectangle([sample_left, sample_top, sample_right, sample_bottom], fill='#aaaaff', outline='black')
    draw.text((sample_right + 10, sample_top + 5), "Обычная задача", fill='black', font=font)

    # Образец выходного дня
    sample_left = 500
    draw.rectangle([sample_left, sample_top, sample_right, sample_bottom], fill='#f0f0f0', outline='lightgray')
    draw.text((sample_right + 10, sample_top + 5), "Выходной день", fill='black', font=font)


def generate_task_colors(tasks):
    """
    Генерирует цвета для задач.

    Args:
        tasks: Список задач

    Returns:
        Словарь с цветами для каждой задачи
    """
    # Цвета для задач (критический путь выделяется красным)
    critical_color = (255, 170, 170)  # Светло-красный

    # Цвета для обычных задач
    normal_colors = [
        (170, 170, 255),  # Светло-синий
        (170, 255, 170),  # Светло-зеленый
        (255, 255, 170),  # Светло-желтый
        (255, 170, 255),  # Светло-фиолетовый
        (170, 255, 255),  # Светло-голубой
    ]

    colors = {}
    color_index = 0

    # Определяем цвета для задач
    for task in tasks:
        if task['is_critical']:
            colors[task['id']] = critical_color
        else:
            colors[task['id']] = normal_colors[color_index % len(normal_colors)]
            color_index += 1

    return colors


def generate_network_diagram(calendar_plan):
    """
    Генерирует сетевую диаграмму проекта.

    Args:
        calendar_plan: Календарный план с задачами

    Returns:
        Изображение сетевой диаграммы в формате PIL.Image
    """
    # Эта функция может быть реализована для создания сетевой диаграммы
    # Однако это требует более сложной логики для расположения узлов и ребер
    # Вместо этого можно использовать библиотеки, такие как networkx и matplotlib

    # Заглушка: создаем пустое изображение
    image = Image.new('RGB', (400, 200), 'white')
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('arial.ttf', 12)
    except IOError:
        font = ImageFont.load_default()
    draw.text((10, 10), "Сетевая диаграмма (в разработке)", fill="black", font=font)
    return image


def export_gantt_to_html(calendar_plan, filename='gantt_chart.html'):
    """
    Экспортирует диаграмму Ганта в HTML файл для интерактивного просмотра.

    Args:
        calendar_plan: Календарный план с задачами
        filename: Имя файла для сохранения

    Returns:
        Путь к созданному HTML файлу
    """
    tasks = calendar_plan['tasks']

    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Диаграмма Ганта</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .gantt-chart { margin-top: 20px; }
            .task-row { height: 30px; border-bottom: 1px solid #eee; }
            .task-name { display: inline-block; width: 250px; padding: 5px; }
            .task-bar-container { display: inline-block; position: relative; }
            .day-column { display: inline-block; width: 30px; height: 30px; text-align: center; border-right: 1px solid #eee; }
            .weekend { background-color: #f8f8f8; }
            .task-bar { position: absolute; height: 20px; top: 5px; border-radius: 3px; border: 1px solid #333; text-align: center; }
            .critical { background-color: #ffaaaa; }
            .normal { background-color: #aaaaff; }
            .header { font-weight: bold; border-bottom: 2px solid #ccc; }
            .date-header { display: inline-block; width: 30px; text-align: center; font-size: 11px; }
        </style>
    </head>
    <body>
        <h1>Диаграмма Ганта</h1>
        <div class="gantt-chart">
    """

    # Определяем временные границы проекта
    start_date = min(task['start_date'] for task in tasks)
    end_date = max(task['end_date'] for task in tasks)
    project_duration = (end_date - start_date).days + 1

    # Создаем заголовок с датами
    html_content += '<div class="header"><div class="task-name">Задача</div><div class="task-bar-container">'

    for i in range(project_duration):
        date = start_date + timedelta(days=i)
        is_weekend = date.weekday() >= 5
        weekend_class = ' weekend' if is_weekend else ''
        html_content += f'<div class="date-header{weekend_class}">{date.strftime("%d.%m")}</div>'

    html_content += '</div></div>'

    # Добавляем задачи
    for task in tasks:
        days_from_start = (task['start_date'] - start_date).days
        task_duration = (task['end_date'] - task['start_date']).days + 1
        task_type = 'critical' if task['is_critical'] else 'normal'

        html_content += f'<div class="task-row">'
        html_content += f'<div class="task-name">{task["name"]} ({task["employee"]})</div>'
        html_content += f'<div class="task-bar-container">'

        # Добавляем колонки для дней
        for i in range(project_duration):
            date = start_date + timedelta(days=i)
            is_weekend = date.weekday() >= 5
            weekend_class = ' weekend' if is_weekend else ''
            html_content += f'<div class="day-column{weekend_class}"></div>'

        # Добавляем полосу задачи
        html_content += f'<div class="task-bar {task_type}" style="left: {days_from_start * 30}px; width: {task_duration * 30 - 10}px;">{task_duration} дн.</div>'

        html_content += '</div></div>'

    html_content += """
        </div>
    </body>
    </html>
    """

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return filename