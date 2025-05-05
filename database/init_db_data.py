# init_db_data.py
from database.operations import init_db, Session
from database.models import Project, Employee, DayOff


def init_predefined_data():
    # Создаем базу данных, если она не существует
    init_db()

    session = Session()
    try:
        # Проверяем, есть ли базовый проект
        base_project = session.query(Project).filter(Project.name == "Базовый проект").first()

        if not base_project:
            # Создаем базовый проект
            base_project = Project(name="Базовый проект")
            session.add(base_project)
            session.flush()

            # Создаем базовых сотрудников
            default_employees = [
                {
                    "name": "Иванов Иван Иванович",
                    "position": "Технический специалист",
                    "days_off": ["Среда", "Пятница"]
                },
                {
                    "name": "Петров Петр Петрович",
                    "position": "Старший тех. специалист",
                    "days_off": ["Суббота", "Воскресенье"]
                },
                {
                    "name": "Сидоров Сидор Сидорович",
                    "position": "Руководитель настройки",
                    "days_off": ["Суббота", "Воскресенье"]
                },
                {
                    "name": "Смирнова Анна Ивановна",
                    "position": "Младший специалист",
                    "days_off": ["Суббота", "Воскресенье"]
                },
                {
                    "name": "Кузнецов Алексей Петрович",
                    "position": "Старший специалист",
                    "days_off": ["Суббота", "Воскресенье"]
                },
                {
                    "name": "Соколова Мария Александровна",
                    "position": "Руководитель контента",
                    "days_off": ["Суббота", "Воскресенье"]
                }
            ]

            for emp_data in default_employees:
                employee = Employee(
                    project_id=base_project.id,
                    name=emp_data["name"],
                    position=emp_data["position"]
                )
                session.add(employee)
                session.flush()

                for day in emp_data["days_off"]:
                    day_off = DayOff(
                        employee_id=employee.id,
                        day=day
                    )
                    session.add(day_off)

            session.commit()
            print("Базовые данные успешно инициализированы")
        else:
            print("Базовые данные уже существуют")

    finally:
        session.close()


if __name__ == "__main__":
    init_predefined_data()