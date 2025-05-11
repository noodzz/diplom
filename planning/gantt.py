from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta

def generate_gantt_chart(calendar_plan):
    """
    Generates a Gantt chart for the calendar plan.

    Args:
        calendar_plan: Calendar plan with tasks

    Returns:
        PIL Image object with the Gantt chart
    """
    # Проверка на наличие задач
    if not calendar_plan or 'tasks' not in calendar_plan or not calendar_plan['tasks']:
        # Создаем пустое изображение с сообщением об ошибке
        image = Image.new('RGB', (400, 200), 'white')
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype('arial.ttf', 12)
        except IOError:
            font = ImageFont.load_default()
        draw.text((10, 10), "Нет задач для отображения", fill="black", font=font)
        return image

    # Идентификация родительских задач (имеют подзадачи)
    parent_task_ids = set()
    for task in calendar_plan['tasks']:
        if task.get('parent_id'):
            parent_task_ids.add(task.get('parent_id'))

    # Фильтруем задачи: показываем или родительские, если нет подзадач, или подзадачи
    filtered_tasks = []
    for task in calendar_plan['tasks']:
        task_id = task.get('id')
        # Если это родительская задача без исполнителя или задача без подзадач
        if (task_id in parent_task_ids and not task.get('is_subtask')) or (task_id not in parent_task_ids):
            filtered_tasks.append(task)

    # Используем отфильтрованные задачи вместо всех задач
    tasks = filtered_tasks

    # Сортируем задачи по дате начала
    sorted_tasks = sorted(tasks, key=lambda x: x['start_date'])
    # Группируем задачи по имени для отображения групповых задач
    tasks_by_name = {}
    for task in calendar_plan['tasks']:
        # Для подзадач (с is_subtask=True) используем уникальный ключ с сотрудником
        if task.get('is_subtask'):
            key = f"{task['name']} - {task.get('employee', 'Не назначен')}"
            if key not in tasks_by_name:
                tasks_by_name[key] = []
            tasks_by_name[key].append(task)
        else:
            # Для обычных задач используем только имя
            name = task['name']
            if name not in tasks_by_name:
                tasks_by_name[name] = []
            tasks_by_name[name].append(task)

    # Сортируем задачи по дате начала
    for task_name, task_group in tasks_by_name.items():
        required_employees = task_group[0].get('required_employees', 1)
        if required_employees > 1:
            # Для групповых задач добавляем все подзадачи
            sorted_tasks.extend(task_group)
        else:
            # Для обычных задач добавляем одну задачу
            sorted_tasks.append(task_group[0])

    sorted_tasks.sort(key=lambda x: x['start_date'])

    # Находим общий временной диапазон
    start_date = min(task['start_date'] for task in sorted_tasks)
    end_date = max(task['end_date'] for task in sorted_tasks)
    total_days = (end_date - start_date).days + 1

    # Параметры изображения
    task_height = 30
    task_spacing = 10
    left_margin = 200
    top_margin = 50
    right_margin = 50
    bottom_margin = 50
    day_width = 20

    # Размеры изображения
    width = left_margin + (total_days * day_width) + right_margin
    height = top_margin + (len(sorted_tasks) * (task_height + task_spacing)) + bottom_margin

    # Создаем изображение
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)

    # Загружаем шрифт с поддержкой кириллицы
    try:
        font = ImageFont.truetype("Arial.ttf", 12)
        title_font = ImageFont.truetype("Arial.ttf", 14)
    except IOError:
        # Если Arial не найден, пробуем другие шрифты
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 12)
            title_font = ImageFont.truetype("DejaVuSans.ttf", 14)
        except IOError:
            # Если и DejaVuSans не найден, используем стандартный шрифт
            font = ImageFont.load_default()
            title_font = ImageFont.load_default()

    # Рисуем заголовок
    draw.text((10, 10), "Диаграмма Ганта", font=title_font, fill='black')

    # Рисуем временную шкалу
    current_date = start_date
    for day in range(total_days):
        x = left_margin + (day * day_width)
        date_str = current_date.strftime('%d.%m')
        draw.text((x, top_margin - 20), date_str, font=font, fill='black')
        current_date += timedelta(days=1)

    # Рисуем задачи
    for i, task in enumerate(sorted_tasks):
        y = top_margin + (i * (task_height + task_spacing))
        
        # Рисуем название задачи
        task_name = task['name']
        required_employees = task.get('required_employees', 1)
        if required_employees > 1:
            task_name = f"{task_name} | {task['employee']}"
        draw.text((10, y + 5), task_name, font=font, fill='black')

        # Вычисляем координаты для полосы задачи
        start_x = left_margin + ((task['start_date'] - start_date).days * day_width)
        end_x = left_margin + ((task['end_date'] - start_date).days * day_width)
        
        # Выбираем цвет в зависимости от типа задачи
        if task['is_critical']:
            color = 'red'
        else:
            color = 'blue'

        # Рисуем полосу задачи
        draw.rectangle([start_x, y, end_x, y + task_height], fill=color, outline='black')

        # Добавляем информацию о длительности
        duration_text = f"{task['duration']} дн."
        text_width = draw.textlength(duration_text, font=font)
        text_x = start_x + ((end_x - start_x - text_width) / 2)
        draw.text((text_x, y + 5), duration_text, font=font, fill='white')

    return image 