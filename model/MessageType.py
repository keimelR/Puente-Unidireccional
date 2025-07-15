from enum import Enum

class MessageType(str, Enum):
    REQUEST = "REQUEST_ACCESS"              # Cliente solicita acceso al puente
    END_CROSS = "CROSSING_COMPLETE"         # Cliente informa que terminó de cruzar
    STATUS_UPDATE = "UPDATE_BRIDGE_STATUS"  # Servidor envía estado del puente a todos
    PERMISSION_GRANTED = "PERMISSION_GRANTED" # Servidor permite cruzar a un coche específico
    PERMISSION_DENIED = "PERMISSION_DENIED"   # Servidor deniega acceso a un coche específico