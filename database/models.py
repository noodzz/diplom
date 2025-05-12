from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Boolean, DateTime, Table, Date as SQLAlchemyDate
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref
from datetime import datetime

from config import DATABASE_URL

Base = declarative_base()

# Новая таблица для связи сотрудник-проект
employee_project = Table(
    'employee_project', Base.metadata,
    Column('employee_id', Integer, ForeignKey('employees.id'), primary_key=True),
    Column('project_id', Integer, ForeignKey('projects.id'), primary_key=True)
)

class Project(Base):
    """Модель проекта в БД."""
    __tablename__ = 'projects'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    start_date = Column(SQLAlchemyDate, nullable=True)

    tasks = relationship("Task", back_populates="project")
    employees = relationship("Employee", secondary=employee_project, back_populates="projects")

    def __repr__(self):
        return f"<Project(id={self.id}, name='{self.name}')>"


class Task(Base):
    """Модель задачи в БД."""
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    name = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)
    position = Column(String, nullable=True)  # Может быть null для родительских задач
    required_employees = Column(Integer, default=1)
    parent_id = Column(Integer, ForeignKey('tasks.id'), nullable=True)  # ID родительской задачи

    project = relationship("Project", back_populates="tasks")
    predecessors = relationship(
        "TaskDependency",
        foreign_keys="[TaskDependency.task_id]",
        back_populates="task"
    )
    subtasks = relationship("Task", backref=backref("parent", remote_side=[id]))  # Связь с подзадачами
    parts = relationship("TaskPart", back_populates="task")  # Связь с частями задачи

    def __repr__(self):
        return f"<Task(id={self.id}, name='{self.name}', duration={self.duration})>"

class TaskDependency(Base):
    """Модель зависимости между задачами в БД."""
    __tablename__ = 'task_dependencies'

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    predecessor_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)

    task = relationship("Task", foreign_keys=[task_id], back_populates="predecessors")
    predecessor = relationship("Task", foreign_keys=[predecessor_id])

    def __repr__(self):
        return f"<TaskDependency(task_id={self.task_id}, predecessor_id={self.predecessor_id})>"


class Employee(Base):
    """Модель сотрудника в БД."""
    __tablename__ = 'employees'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    position = Column(String, nullable=False)
    email = Column(String, nullable=True)

    projects = relationship("Project", secondary=employee_project, back_populates="employees")
    days_off = relationship("DayOff", back_populates="employee")

    def __repr__(self):
        return f"<Employee(id={self.id}, name='{self.name}', position='{self.position}')>"


class DayOff(Base):
    """Модель выходного дня сотрудника в БД."""
    __tablename__ = 'days_off'

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('employees.id'), nullable=False)
    day = Column(String, nullable=False)  # Название дня недели

    employee = relationship("Employee", back_populates="days_off")

    def __repr__(self):
        return f"<DayOff(employee_id={self.employee_id}, day='{self.day}')>"


class ProjectTemplate(Base):
    """Модель шаблона проекта в БД."""
    __tablename__ = 'project_templates'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    tasks = relationship("TaskTemplate", back_populates="project_template")

    def __repr__(self):
        return f"<ProjectTemplate(id={self.id}, name='{self.name}')>"


class TaskTemplate(Base):
    """Модель шаблона задачи в БД."""
    __tablename__ = 'task_templates'

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey('project_templates.id'), nullable=False)
    name = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)
    position = Column(String, nullable=False)
    order = Column(Integer, nullable=False)  # Порядок задачи в шаблоне
    required_employees = Column(Integer, default=1)  # Number of required employees
    roles_info = Column(String, nullable=True)  # Формат: "Должность1:длительность1|Должность2:длительность2"
    sequential_subtasks = Column(Boolean, default=False)  # Выполнять подзадачи последовательно

    project_template = relationship("ProjectTemplate", back_populates="tasks")
    dependencies = relationship(
        "TaskTemplateDependency",
        foreign_keys="[TaskTemplateDependency.task_id]",
        back_populates="task"
    )

    def __repr__(self):
        return f"<TaskTemplate(id={self.id}, name='{self.name}', duration={self.duration})>"

class TaskTemplateDependency(Base):
    """Модель зависимости между шаблонами задач в БД."""
    __tablename__ = 'task_template_dependencies'

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('task_templates.id'), nullable=False)
    predecessor_id = Column(Integer, ForeignKey('task_templates.id'), nullable=False)

    task = relationship("TaskTemplate", foreign_keys=[task_id], back_populates="dependencies")
    predecessor = relationship("TaskTemplate", foreign_keys=[predecessor_id])

    def __repr__(self):
        return f"<TaskTemplateDependency(task_id={self.task_id}, predecessor_id={self.predecessor_id})>"

class AllowedUser(Base):
    """Модель разрешенного пользователя в БД."""
    __tablename__ = 'allowed_users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    name = Column(String, nullable=True)
    added_by = Column(Integer, nullable=True)  # ID администратора, добавившего пользователя
    added_at = Column(DateTime, default=datetime.now)
    is_admin = Column(Boolean, default=False)  # Флаг администратора

    def __repr__(self):
        return f"<AllowedUser(telegram_id={self.telegram_id}, name='{self.name}')>"

class TaskPart(Base):
    """Модель части задачи в БД."""
    __tablename__ = 'task_parts'

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    name = Column(String, nullable=False)
    position = Column(String, nullable=False)  # Должность для этой части
    duration = Column(Integer, nullable=False)  # Длительность этой части в днях
    order = Column(Integer, nullable=False)  # Порядок выполнения части
    required_employees = Column(Integer, default=1)

    task = relationship("Task", back_populates="parts")

    def __repr__(self):
        return f"<TaskPart(id={self.id}, name='{self.name}', position='{self.position}')>"