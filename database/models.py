from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

from config import DATABASE_URL

Base = declarative_base()


class Project(Base):
    """Модель проекта в БД."""
    __tablename__ = 'projects'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    tasks = relationship("Task", back_populates="project")
    employees = relationship("Employee", back_populates="project")

    def __repr__(self):
        return f"<Project(id={self.id}, name='{self.name}')>"


class Task(Base):
    """Модель задачи в БД."""
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    name = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)
    position = Column(String, nullable=False)
    required_employees = Column(Integer, default=1)  # Add this line

    project = relationship("Project", back_populates="tasks")
    predecessors = relationship(
        "TaskDependency",
        foreign_keys="[TaskDependency.task_id]",
        back_populates="task"
    )

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
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    name = Column(String, nullable=False)
    position = Column(String, nullable=False)
    email = Column(String, nullable=True)

    project = relationship("Project", back_populates="employees")
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
