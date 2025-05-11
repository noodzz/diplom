"""
Модуль для визуализации календарного плана в виде диаграммы Ганта
"""

from PIL import Image, ImageDraw, ImageFont
from datetime import timedelta, datetime
import random


def generate_gantt_chart(calendar_plan):
    """
    Generates a clean, professional Gantt chart for the calendar plan with diagonal date labels.
    Fixed for float/integer conversion issues.

    Args:
        calendar_plan: Calendar plan with tasks

    Returns:
        PIL Image object with the Gantt chart
    """
    # Check if we have tasks
    if not calendar_plan or 'tasks' not in calendar_plan or not calendar_plan['tasks']:
        image = Image.new('RGB', (400, 200), 'white')
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype('arial.ttf', 12)
        except IOError:
            font = ImageFont.load_default()
        draw.text((10, 10), "Нет задач для отображения", fill="black", font=font)
        return image

    # Group tasks by name - only keep parent tasks and standalone tasks
    consolidated_tasks = {}
    for task in calendar_plan['tasks']:
        # Skip subtasks with "is_subtask" flag or that have text in name like "- Position"
        if task.get('is_subtask') or " - " in task.get('name', ""):
            continue

        task_name = task['name']

        if task_name not in consolidated_tasks:
            consolidated_tasks[task_name] = task.copy()
        else:
            # Update start/end dates if necessary
            existing = consolidated_tasks[task_name]
            if task['start_date'] < existing['start_date']:
                existing['start_date'] = task['start_date']
            if task['end_date'] > existing['end_date']:
                existing['end_date'] = task['end_date']

            # Keep critical flag if either is critical
            if task.get('is_critical'):
                existing['is_critical'] = True

    # Convert to list and sort by start date
    tasks = list(consolidated_tasks.values())
    tasks.sort(key=lambda x: (not x.get('is_critical', False), x['start_date']))

    # Find time boundaries
    start_date = min(task['start_date'] for task in tasks)
    end_date = max(task['end_date'] for task in tasks)
    total_days = (end_date - start_date).days + 1

    # Chart parameters - ensure all are integers
    task_height = 30
    task_spacing = 15
    left_margin = 150
    top_margin = 80
    right_margin = 50
    bottom_margin = 60
    day_width = 30

    # Calculate dimensions - ensure integers
    width = left_margin + (total_days * day_width) + right_margin
    height = top_margin + (len(tasks) * (task_height + task_spacing)) + bottom_margin

    # Create image with white background
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)

    # Try to load fonts
    try:
        title_font = ImageFont.truetype("Arial.ttf", 16)
        header_font = ImageFont.truetype("Arial.ttf", 12)
        task_font = ImageFont.truetype("Arial.ttf", 12)
        small_font = ImageFont.truetype("Arial.ttf", 10)
    except IOError:
        try:
            title_font = ImageFont.truetype("DejaVuSans.ttf", 16)
            header_font = ImageFont.truetype("DejaVuSans.ttf", 12)
            task_font = ImageFont.truetype("DejaVuSans.ttf", 12)
            small_font = ImageFont.truetype("DejaVuSans.ttf", 10)
        except IOError:
            title_font = ImageFont.load_default()
            header_font = ImageFont.load_default()
            task_font = ImageFont.load_default()
            small_font = ImageFont.load_default()

    # Draw title
    try:
        text_width = draw.textlength("Диаграмма Ганта проекта", font=title_font)
    except (AttributeError, TypeError):
        text_width = 200  # Fallback width

    title_x = max(0, (width // 2) - (int(text_width) // 2))
    draw.text((title_x, 10), "Диаграмма Ганта проекта", fill="black", font=title_font)

    # Draw time scale with vertical grid lines
    current_date = start_date
    for day in range(total_days + 1):
        x = left_margin + (day * day_width)

        # Vertical grid line
        line_color = '#e0e0e0'
        draw.line([(x, top_margin), (x, height - bottom_margin)], fill=line_color, width=1)

        # Draw diagonal date labels
        date_str = current_date.strftime('%d.%m')

        # Calculate text dimensions
        try:
            text_width = draw.textlength(date_str, font=header_font)
        except (AttributeError, TypeError):
            text_width = len(date_str) * 7  # Approximate width

        text_height = 15  # Approximate height of text
        txt_img = Image.new('RGBA', (int(text_width), text_height), (255, 255, 255, 0))
        txt_draw = ImageDraw.Draw(txt_img)
        txt_draw.text((0, 0), date_str, font=header_font, fill='black')

        # Rotate the text image
        rotated_txt = txt_img.rotate(45, expand=1)

        # Calculate paste position and ensure integers
        paste_x = max(0, x - 5)
        paste_y = max(0, top_margin - rotated_txt.height - 5)

        # Paste the rotated text onto the main image
        image.paste(rotated_txt, (paste_x, paste_y), rotated_txt)

        # Weekend highlighting (Saturday=5, Sunday=6)
        if current_date.weekday() >= 5:
            draw.rectangle(
                [(x, top_margin), (x + day_width, height - bottom_margin)],
                fill='#f5f5f5',
                outline=None
            )

        current_date += timedelta(days=1)

    # Draw horizontal grid lines
    for i in range(len(tasks) + 1):
        y = top_margin + i * (task_height + task_spacing)
        draw.line([(left_margin, y), (width - right_margin, y)], fill='#e0e0e0', width=1)

    # Draw tasks
    for i, task in enumerate(tasks):
        y = top_margin + i * (task_height + task_spacing)

        # Draw task name
        task_name = task['name']
        draw.text((10, y + 10), task_name, font=task_font, fill='black')

        # Calculate task bar position - ensure integers
        days_from_start = (task['start_date'] - start_date).days
        task_duration = (task['end_date'] - task['start_date']).days + 1

        start_x = left_margin + (days_from_start * day_width)
        end_x = left_margin + ((days_from_start + task_duration) * day_width)

        # Determine color based on criticality
        if task.get('is_critical', False):
            fill_color = '#ff7070'  # Red for critical tasks
            outline_color = '#cc0000'
        else:
            fill_color = '#70a0ff'  # Blue for normal tasks
            outline_color = '#0055cc'

        # Draw task bar
        draw.rectangle(
            [start_x, y + 5, end_x - 5, y + task_height - 5],
            fill=fill_color,
            outline=outline_color,
            width=2
        )

        # Add crosshatch pattern to critical tasks
        if task.get('is_critical', False):
            for line_x in range(start_x, int(end_x), 7):  # Ensure integer for range
                draw.line(
                    [(line_x, y + 5), (line_x + 7, y + task_height - 5)],
                    fill='#cc0000',
                    width=1
                )

        # Add duration text
        duration_text = f"{task_duration}д."
        try:
            text_width = draw.textlength(duration_text, font=small_font)
        except (AttributeError, TypeError):
            text_width = len(duration_text) * 6  # Approximate width

        # Calculate centered position and ensure integers
        text_x = start_x + ((end_x - start_x - int(text_width)) // 2)
        draw.text(
            (text_x, y + 10),
            duration_text,
            font=small_font,
            fill='white'
        )

    # Draw legend
    legend_y = height - bottom_margin + 10

    # Critical task
    draw.rectangle([20, legend_y, 50, legend_y + 20], fill='#ff7070', outline='#cc0000', width=2)
    for line_x in range(20, 50, 7):
        draw.line([(line_x, legend_y), (line_x + 7, legend_y + 20)], fill='#cc0000', width=1)
    draw.text((55, legend_y + 3), "Критическая задача", font=task_font, fill='black')

    # Normal task
    draw.rectangle([230, legend_y, 260, legend_y + 20], fill='#70a0ff', outline='#0055cc', width=2)
    draw.text((265, legend_y + 3), "Обычная задача", font=task_font, fill='black')

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