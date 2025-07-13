from model.Vehicle import Vehicle
from model.MessageType import MessageType
from model.Direccion import Direccion

import random
import socket
import json
import time

class Client:
    """
    Representacion logica del cliente y sus acciones
    """
    def __init__(
        self,
        id,
        host,
        port,
        velocidad,
        tiempo_retraso,
        direccion,
        tiempo_reingreso
    ):
        """
        Constructor
        
        Args:
            host: Host del cliente
            port: Puerto del cliente
            client_socket: Socket para el cliente
            velocidad: Velocidad del vehiculo
            tiempo_retraso: Tiempo promedio de retraso después de cruzar
            direccion: Direccion del vehiculo
            tiempo_reingreso: Tiempo para cruzar nuevamente el puente
        """
        self.host = host
        self.port = port
        self.client_socket = None
        
        self.vehicle = Vehicle(
            id = id,
            velocidad = velocidad,
            tiempo_retraso = tiempo_retraso,
            direccion = direccion 
        )
        self.tiempo_reingreso = tiempo_reingreso
        
    def conexion(self):
        """
        Establece la conexion del socket del cliente con el servidor
        """
        self.client_socket = socket.socket(socket.AddressFamily.AF_INET, socket.SocketKind.SOCK_STREAM)
        self.client_socket.connect((self.host, self.port))
        
    def enviar(self, message_type):
        """
        Establece el intercambio de mensajes entre el cliente y el servidor
        
        Args:
            message_type: El tipo de mensaje enviado al servidor (define la accion del vehiculo)
        """
        mensaje = self.mensaje_template(message_type = message_type)
        
        self.client_socket.send(json.dumps(mensaje).encode())
        respuesta = self.client_socket.recv(1024)
        return json.loads(respuesta.decode())
        
    def cruzar(self):
        """
        Establece las acciones del vehiculo para cruzar el puente
        """
        while True:   
            # Envia una solicitud para cruzar el puente
            resp = self.enviar(MessageType.REQUEST.value)
            print(f"[{self.vehicle.id}] Estado: {resp['status']} - {resp['message']}")
            
            # Si la respuesta de la solicitud es afirmativa
            if resp['status'] == "Exitoso":
                
                # Simula tiempo en el puente
                tiempo_cruce = random.uniform(1, self.vehicle.velocidad)
                print(f"[{self.vehicle.id}] Cruzando puente por {tiempo_cruce:.2f} segundos...")
                time.sleep(tiempo_cruce)
                
                # Notifica fin de cruce                
                self.enviar(MessageType.END_CROSS.value)
                print(f"[{self.vehicle.id}] Terminó de cruzar.")
                
                # Espera antes de volver a intentar
                tiempo_espera = random.uniform(1, self.vehicle.tiempo_retraso)
                print(f"[{self.vehicle.id}] Esperando {tiempo_espera:.2f} segundos antes de volver a cruzar.")
                time.sleep(tiempo_espera)
                
                # Cambia dirección para simular tráfico bidireccional
                self.direccion = Direccion.LEFT if self.vehicle.direccion == Direccion.RIGHT else Direccion.RIGHT
            else:
                # Espera antes de volver a solicitar
                time.sleep(1)

    def mensaje_template(self, message_type):
        """
        Template para enviar un mensaje (token) al servidor
        
        Args:
            message_type: El tipo de mensaje (token) enviado al servidor
            
        Returns:
            dict[str, Any]: Representa el JSON enviado al servidor
        """
        return {
            'id': self.vehicle.id,
            'direction': self.vehicle.direccion,
            'type': message_type
        }
        
    def cerrar(self):
        self.client_socket.close()