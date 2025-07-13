from enum import Enum

class MessageType(str, Enum):
    """
    Solicitudes del cliente para el servidor (TOKENS)
    """
    REQUEST = "REQUEST_CROSS"
    END_CROSS = "FINISHED_CROSSING"
    STATUS = "GET_STATUS"