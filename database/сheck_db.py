# Создайте временный скрипт check_db.py
from database.operations import Session
from database.models import Employee

session = Session()
try:
    print("Сотрудники в базе данных:")
    employees = session.query(Employee).all()
    for emp in employees:
        print(f"ID: {emp.id}, Имя: {emp.name}, Должность: '{emp.position}', Проект ID: {emp.project_id}")
    
    print("\nУникальные должности:")
    positions = session.query(Employee.position).distinct().all()
    for pos in positions:
        print(f"  - '{pos[0]}'")
finally:
    session.close()