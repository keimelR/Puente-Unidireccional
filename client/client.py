import sys
import os
import logging
import datetime
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model.Vehicle import Vehicle
from model.MessageType import MessageType
from model.Direccion import Direccion

import random
import socket
import json
import time

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Client:
    """
    Representacion logica del cliente y sus acciones
    """
    MAX_RETRIES = 5
    
    def __init__(
        self,
        id,
        host,
        port,
        velocidad,
        tiempo_retraso,
        direccion
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
        
        self.conexion()  # Establecer conexión persistente al crear el cliente
        
    def conexion(self):
        try:
            self.client_socket = socket.socket(socket.AddressFamily.AF_INET, socket.SocketKind.SOCK_STREAM)
            self.client_socket.settimeout(None)
            self.client_socket.connect((self.host, self.port))
            logger.info(f"[{self.vehicle.id}] Conectado a {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"[ERROR] Fallo al conectar con el servidor: {e}")
            sys.exit(1)
        
    def enviar(self, message_type):
        """
        Envía un mensaje al servidor usando el socket persistente y espera la respuesta.
        """
        if self.client_socket is None:
            raise RuntimeError("El socket del cliente no está inicializado. Llama a self.conexion() antes de enviar mensajes.")
        mensaje = self.mensaje_template(message_type=message_type)
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                self.client_socket.send((json.dumps(mensaje) + "\n").encode())
                respuesta = b""
                while True:
                    parte = self.client_socket.recv(1024)
                    if not parte:
                        raise ConnectionResetError("Conexión cerrada por el servidor.")
                    respuesta += parte
                    if b"\n" in respuesta:
                        msg_bytes, respuesta = respuesta.split(b"\n", 1)
                        logger.debug(f"[DEBUG CLIENTE] Respuesta cruda recibida: {msg_bytes}")
                        return json.loads(msg_bytes.decode())
                raise RuntimeError("No se recibió respuesta del servidor.")
            except (socket.timeout, ConnectionResetError, BrokenPipeError) as e:
                retries += 1
                logger.warning(f"[ERROR] Problema de red o timeout: {e}. Intentando reconectar ({retries}/{self.MAX_RETRIES})...")
                self.cerrar()
                time.sleep(1)
                self.conexion()
        logger.error(f"[FATAL] Se superó el máximo de intentos de reconexión ({self.MAX_RETRIES}). Cerrando cliente.")
        self.cerrar()
        sys.exit(1)

    def cruzar(self):
        """
        Establece las acciones del vehiculo para cruzar el puente
        """
        try:
            while True:   
                # Envia una solicitud para cruzar el puente
                resp = self.enviar(MessageType.REQUEST.value)
                logger.info(f"[{self.vehicle.id}] Estado: {resp['status']} - {resp['message']}")
                
                # Si la respuesta de la solicitud es afirmativa
                if resp['status'] == "Exitoso":
                    # Simula tiempo en el puente
                    tiempo_cruce = random.uniform(1, self.vehicle.velocidad)
                    logger.info(f"[{self.vehicle.id}] Cruzando puente por {tiempo_cruce:.2f} segundos...")
                    time.sleep(tiempo_cruce)
                    
                    # Notifica fin de cruce                
                    resp_end = self.enviar(MessageType.END_CROSS.value)
                    logger.info(f"[{self.vehicle.id}] Terminó de cruzar. Respuesta: {resp_end}")
                    
                    # Espera antes de volver a intentar
                    tiempo_espera = random.uniform(1, self.vehicle.tiempo_retraso)
                    logger.info(f"[{self.vehicle.id}] Esperando {tiempo_espera:.2f} segundos antes de volver a cruzar.")
                    time.sleep(tiempo_espera)
                    
                    # Cambia dirección para simular tráfico bidireccional
                    self.vehicle.cambiar_direccion()  # type: ignore
                    logger.info(f"[{self.vehicle.id}] Cambia dirección a: {self.vehicle.direccion.value}")
                else:
                    logger.info(f"[{self.vehicle.id}] Esperando para volver a intentar...")
                    # Espera antes de volver a solicitar
                    time.sleep(1)
        finally:
            self.cerrar()

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
            'direction': self.vehicle.direccion.value,
            'type': message_type,
            'timestamp': datetime.datetime.utcnow().isoformat()
        }
        
    def cerrar(self):
        if self.client_socket is not None:
            self.client_socket.close()
            self.client_socket = None

if __name__ == "__main__":
    print("=== Cliente de Puente Unidireccional ===")
    id_vehiculo = input("ID del vehículo: ")
    host = "127.0.0.1"
    port = 7777
    velocidad = float(input("Velocidad máxima (segundos en puente, ej: 3): "))
    tiempo_retraso = float(input("Tiempo de retraso tras cruzar (segundos, ej: 2): "))
    
    # Validación de dirección inicial
    dir_inicial = input("Dirección inicial [left/right]: ").strip().lower()
    if dir_inicial not in ["left", "right"]:
        print("Dirección inválida. Debe ser 'left' o 'right'.")
        sys.exit(1)
    
    if dir_inicial == "right":
        direccion = Direccion.RIGHT
    else:
        direccion = Direccion.LEFT

    client = Client(
        id=id_vehiculo,
        host=host,
        port=port,
        velocidad=velocidad,
        tiempo_retraso=tiempo_retraso,
        direccion=direccion
    )
    try:
        client.cruzar()
    except KeyboardInterrupt:
        logger.info("Cerrando cliente...")
        client.cerrar()