from enum import Enum

class Direccion(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    NONE = "NONE"  # Para cuando el puente está libre