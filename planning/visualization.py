# planning/visualization.py
"""
Модуль для визуализации календарного плана в виде диаграммы Ганта
"""

from PIL import Image, ImageDraw, ImageFont
from datetime import timedelta, datetime
import random


def generate_gantt_chart(calendar_plan):
    """
    Generates a Gantt chart image for a calendar plan.

    Args:
        calendar_plan: Calendar plan with tasks and dates

    Returns:
        PIL.Image of the Gantt chart
    """
    # Check if there are tasks in the calendar plan
    if not calendar_plan or 'tasks' not in calendar_plan or not calendar_plan['tasks']:
        # Create empty image with error message
        image = Image.new('RGB', (400, 200), 'white')
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype('arial.ttf', 12)
        except IOError:
            font = ImageFont.load_default()
        draw.text((10, 10), "Нет задач для отображения", fill="black", font=font)
        return image

    tasks = calendar_plan['tasks']

    # Ensure all tasks have required fields
    for task in tasks:
        if 'start_date' not in task or 'end_date' not in task:
            print(f"Task missing dates: {task.get('name', 'unknown')}")

        # Provide default values for missing fields to prevent errors
        if 'is_critical' not in task:
            task['is_critical'] = False

    # Determine time boundaries
    try:
        start_date = min(task['start_date'] for task in tasks)
        end_date = max(task['end_date'] for task in tasks)
        project_duration = (end_date - start_date).days + 1
    except (TypeError, KeyError, ValueError) as e:
        # Create empty image with error message
        image = Image.new('RGB', (500, 200), 'white')
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype('arial.ttf', 12)
        except IOError:
            font = ImageFont.load_default()
        draw.text((10, 10), f"Ошибка при определении временных границ: {str(e)}", fill="black", font=font)
        return image

    # Image settings
    task_height = 30
    day_width = 30
    # Reduce margin_left since we don't need space for employee names
    margin_left = 200  # Reduced from 300
    margin_top = 60
    legend_height = 50

    # Create image
    image_width = margin_left + day_width * project_duration
    image_height = margin_top + task_height * len(tasks) + legend_height

    image = Image.new('RGB', (image_width, image_height), 'white')
    draw = ImageDraw.Draw(image)

    # Try to load fonts
    try:
        title_font = ImageFont.truetype('arial.ttf', 16)
        font = ImageFont.truetype('arial.ttf', 12)
        small_font = ImageFont.truetype('arial.ttf', 10)
    except IOError:
        title_font = ImageFont.load_default()
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # Add title
    title = "Диаграмма Ганта проекта"
    draw.text((image_width // 2 - len(title) * 4, 10), title, fill='black', font=title_font)

    # Draw time scale and grid - update the function to reflect the removal of the employee column
    draw_time_scale(draw, start_date, project_duration, margin_left, margin_top, day_width,
                    image_height - legend_height, font)

    # Generate colors for tasks
    colors = generate_task_colors(tasks)

    # Sort tasks by start date to make the chart more readable
    sorted_tasks = sorted(tasks, key=lambda x: x['start_date'])

    # Draw each task
    for i, task in enumerate(sorted_tasks):
        y = margin_top + i * task_height + 5

        # Draw task name
        task_name = task['name']
        if len(task_name) > 30:
            task_name = task_name[:27] + "..."
        draw.text((10, y + 5), task_name, fill='black', font=font)

        # Task coordinates
        days_from_start = (task['start_date'] - start_date).days
        task_duration = (task['end_date'] - task['start_date']).days + 1

        left = margin_left + days_from_start * day_width
        top = y
        right = left + task_duration * day_width
        bottom = top + task_height - 10

        # Determine task color
        color = colors[task['id']]

        # Draw task rectangle
        draw.rectangle([left, top, right, bottom], fill=color, outline='black')

        # Add hatching for critical tasks
        if task['is_critical']:
            draw_hatching(draw, left, top, right, bottom)

        # Task duration text
        duration_text = f"{task_duration}д."
        text_width = len(duration_text) * 6

        # Check if there's enough space for text
        if right - left > text_width + 10:
            draw.text((left + 5, top + 5), duration_text, fill='black', font=small_font)

    # Add legend
    draw_legend(draw, image_width, image_height, legend_height, font)

    return image


def draw_time_scale(draw, start_date, duration, margin_left, margin_top, day_width, image_height, font):
    """
    Draws the time scale and grid for the Gantt chart.

    Args:
        draw: ImageDraw object
        start_date: Project start date
        duration: Project duration in days
        margin_left: Left margin
        margin_top: Top margin
        day_width: Width of one day
        image_height: Height of the image
        font: Font for text
    """
    # Draw horizontal grid lines
    for y in range(margin_top, image_height, 30):
        draw.line([(0, y), (margin_left + duration * day_width, y)], fill='lightgray')

    # Draw vertical grid lines and date markers
    for i in range(duration + 1):
        date = start_date + timedelta(days=i)
        x = margin_left + i * day_width

        # Vertical line
        draw.line([(x, margin_top - 20), (x, image_height)], fill='lightgray')

        # Date label - show every second day to save space
        if i % 2 == 0:
            date_text = date.strftime('%d.%m')
            draw.text((x - 15, margin_top - 20), date_text, fill='black', font=font)

        # Highlight weekends
        if date.weekday() >= 5:  # 5=Saturday, 6=Sunday
            draw.rectangle(
                [(x, margin_top), (x + day_width, image_height)],
                fill='#f0f0f0',
                outline=None
            )

    # Add column header for tasks only (no employee column)
    draw.text((10, margin_top - 20), "Задача", fill='black', font=font)

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

        # Метка даты - отображаем только каждый второй день для экономии места
        if i % 2 == 0:
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
    draw.text((margin_left - 150, margin_top - 20), "Исполнитель", fill='black', font=font)


def draw_task(draw, task, index, start_date, margin_left, margin_top, day_width, task_height, colors, font, small_font):
    """
    Draws a task on the Gantt chart.

    Args:
        draw: ImageDraw object
        task: Task data
        index: Task index
        start_date: Project start date
        margin_left: Left margin
        margin_top: Top margin
        day_width: Width of one day
        task_height: Height of task bar
        colors: Dictionary of colors for tasks
        font: Main font
        small_font: Small font for duration text
    """
    y = margin_top + index * task_height + 5

    # Draw task name
    task_name = task['name']
    if len(task_name) > 30:
        task_name = task_name[:27] + "..."
    draw.text((10, y + 5), task_name, fill='black', font=font)

    # Draw position name instead of employee name
    # Get display name (position or empty string)
    display_name = task.get('display_name', '')
    if display_name:
        draw.text((margin_left - 100, y + 5), display_name, fill='black', font=font)

    # Task coordinates
    days_from_start = (task['start_date'] - start_date).days
    task_duration = (task['end_date'] - task['start_date']).days + 1

    left = margin_left + days_from_start * day_width
    top = y
    right = left + task_duration * day_width
    bottom = top + task_height - 10

    # Determine task color
    color = colors[task['id']]

    # Draw task rectangle
    draw.rectangle([left, top, right, bottom], fill=color, outline='black')

    # Add hatching for critical tasks
    if task['is_critical']:
        draw_hatching(draw, left, top, right, bottom)

    # Duration text
    duration_text = f"{task_duration}д."
    text_width = len(duration_text) * 6

    # Check if there's enough space for text
    if right - left > text_width + 10:
        draw.text((left + 5, top + 5), duration_text, fill='black', font=small_font)


def format_employee_name(full_name):
    """
    Форматирует полное имя сотрудника в формат "Фамилия И.О."

    Args:
        full_name: Полное имя сотрудника (Фамилия Имя Отчество)

    Returns:
        Сокращенное имя в формате "Фамилия И.О."
    """
    parts = full_name.split()

    if len(parts) >= 3:
        # Если есть фамилия, имя и отчество
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
    elif len(parts) == 2:
        # Если есть только фамилия и имя
        return f"{parts[0]} {parts[1][0]}."
    else:
        # Если передано только одно слово или пустая строка
        return full_name


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
    sample_right = sample_left + 40  # Убедимся, что sample_right > sample_left
    sample_bottom = sample_top + 20  # Убедимся, что sample_bottom > sample_top

    # Образец критической задачи
    draw.rectangle([sample_left, sample_top, sample_right, sample_bottom], fill='#ffaaaa', outline='black')
    draw_hatching(draw, sample_left, sample_top, sample_right, sample_bottom)
    draw.text((sample_right + 10, sample_top + 5), "Критическая задача", fill='black', font=font)

    # Образец обычной задачи
    sample_left = 300
    sample_right = sample_left + 40  # Обновляем sample_right после изменения sample_left
    draw.rectangle([sample_left, sample_top, sample_right, sample_bottom], fill='#aaaaff', outline='black')
    draw.text((sample_right + 10, sample_top + 5), "Обычная задача", fill='black', font=font)

    # Образец выходного дня
    sample_left = 500
    sample_right = sample_left + 40  # Обновляем sample_right после изменения sample_left
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
