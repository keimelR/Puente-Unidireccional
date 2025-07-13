from enum import Enum

class Direccion(str, Enum):
    """
    Direcciones de trafico del puente y del vehiculo
    """
    LEFT = "left"
    RIGHT = "right"
    NONE = "none"