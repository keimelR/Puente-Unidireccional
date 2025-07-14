from model.Direccion import Direccion

class Vehicle:
    """
    Representacion logica de las caracteristicas de los vehiculos que cruzan el puente
    """
    def __init__(
        self,
        id: str,
        velocidad: float = 0.0,
        tiempo_retraso: float = 0.0,
        direccion: Direccion = Direccion.NONE
    ):
        """
        Constructor de la clase
        
        Args:
            id (str): Identificador unico del vehiculo
            velocidad (float): Velocidad del vehiculo en el puente 
            tiempo_retraso (float): Tiempo promedio despues de cruzar del vehiculo antes de intentar otro cruce
            direccion (Direccion): Direccion de rumbo inicial del vehiculo
        """
        self.id = id
        self.velocidad = velocidad
        self.tiempo_retraso = tiempo_retraso
        self.direccion = direccion 
        
    def cambiar_direccion(self):
        """
        Cambia la dirección del vehículo (LEFT <-> RIGHT)
        """
        self.direccion = Direccion.LEFT if self.direccion == Direccion.RIGHT else Direccion.RIGHT 