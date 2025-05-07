from enum import Enum, auto

class BotStates(Enum):
    """Состояния для диалогового интерфейса бота."""
    MAIN_MENU = auto()
    SELECT_PROJECT_TYPE = auto()
    CREATE_PROJECT = auto()
    SELECT_TEMPLATE = auto()
    UPLOAD_CSV = auto()
    ADD_TASK = auto()
    ADD_DEPENDENCIES = auto()
    ADD_EMPLOYEES = auto()
    ADD_EMPLOYEE_NAME = auto()
    ADD_EMPLOYEE_POSITION = auto()
    ADD_EMPLOYEE_DAYS_OFF = auto()
    CALCULATE_PLAN = auto()
    SHOW_PLAN = auto()
    SELECT_PROJECT = auto()
    SET_START_DATE = auto()
    SET_PROJECT_START_DATE = auto()
    SELECT_POSITION = auto()
    SELECT_EMPLOYEE = auto()
    PREVIEW_BEFORE_EXPORT = auto()