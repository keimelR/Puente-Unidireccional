import sys
import os
import logging
import datetime
from datetime import timezone
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model.Vehicle import Vehicle
from model.MessageType import MessageType
from model.Direccion import Direccion

import random
import socket
import json
import time
import threading

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
        self.is_connected = False
        self.is_running = True # Para controlar la ejecución del hilo receptor
        
        self.vehicle = Vehicle(
            id = id,
            velocidad = velocidad,
            tiempo_retraso = tiempo_retraso,
            direccion = direccion 
        )
        self.permission_event = threading.Event()
        self.last_server_message = None
        self.lock = threading.Lock()
        
        # Iniciar la conexión y el hilo receptor al crear el cliente
        self.conexion()
        if self.is_connected:
            self.receiver_thread = threading.Thread(target=self.listen_server, daemon=True)
            self.receiver_thread.start()
        
    def conexion(self):
        retries = 0
        while retries < self.MAX_RETRIES and not self.is_connected:
            try:
                if self.client_socket:
                    self.client_socket.close() # Asegurarse de que el socket anterior esté cerrado
                self.client_socket = socket.socket(socket.AddressFamily.AF_INET, socket.SocketKind.SOCK_STREAM)
                self.client_socket.settimeout(5) # Timeout más largo para evitar logs innecesarios de socket.timeout
                self.client_socket.connect((self.host, self.port))
                self.is_connected = True
                logger.info(f"[{self.vehicle.id}] Conectado a {self.host}:{self.port}")
                break
            except (socket.error, OSError) as e:
                retries += 1
                logger.warning(f"[ERROR] Fallo al conectar con el servidor: {e}. Reintentando ({retries}/{self.MAX_RETRIES})...")
                time.sleep(2 ** retries) # Espera exponencial
        if not self.is_connected:
            logger.error(f"[FATAL] No se pudo conectar con el servidor después de {self.MAX_RETRIES} intentos. Cerrando cliente.")
            self.is_running = False
            sys.exit(1)
            
    def _send_raw_message(self, message):
        """Envía un mensaje JSON al servidor sin esperar respuesta."""
        if not self.is_connected or self.client_socket is None:
            logger.error(f"[{self.vehicle.id}] No se pudo enviar el mensaje, el cliente no está conectado.")
            return False
        
        try:
            message_str = json.dumps(message) + "\n"
            self.client_socket.sendall(message_str.encode('utf-8'))
            logger.debug(f"[{self.vehicle.id}] Mensaje enviado: {message['type']}")
            return True
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            logger.error(f"[{self.vehicle.id}] Error al enviar mensaje: {e}. Reconectando...")
            self.is_connected = False
            self.conexion() # Intentar reconectar
            return False
        except Exception as e:
            logger.error(f"[{self.vehicle.id}] Error inesperado al enviar mensaje: {e}")
            return False

    def listen_server(self):
        """
        Hilo receptor que escucha mensajes del servidor y actualiza el estado del cliente.
        """
        buffer = b""
        while self.is_running:
            if not self.is_connected or self.client_socket is None:
                time.sleep(1) # Esperar antes de reintentar si no está conectado
                continue
            try:
                data = self.client_socket.recv(4096)
                if not data: # Servidor cerró la conexión
                    logger.warning(f"[{self.vehicle.id}] Servidor desconectado. Intentando reconectar...")
                    self.is_connected = False
                    self.conexion()
                    continue
                
                buffer += data
                while b"\n" in buffer:
                    msg_bytes, buffer = buffer.split(b"\n", 1)
                    if not msg_bytes.strip(): # Saltar líneas vacías
                        continue
                    try:
                        message = json.loads(msg_bytes.decode('utf-8'))
                        with self.lock:
                            self.last_server_message = message
                        logger.info(f"[{self.vehicle.id}] Recibido del servidor: {message.get('type', message.get('status'))} - {message.get('message')}")
                        
                        # Activar evento si se concede permiso
                        if (message.get('status') == MessageType.PERMISSION_GRANTED.value):
                            expected_dir = message.get('expected_direction')
                            if expected_dir and self.vehicle.direccion.value != expected_dir:
                                # Si el servidor indica una dirección esperada diferente a la actual del cliente,
                                # la actualizamos. Esto es crucial si el scheduler del servidor está intentando
                                # coordinar la dirección.
                                logger.info(f"[{self.vehicle.id}] Ajustando dirección a la esperada por el servidor: {expected_dir}")
                                self.vehicle.direccion = Direccion(expected_dir)
                            self.permission_event.set() # Activa el evento para la lógica de cruce
                        elif (message.get('status') == MessageType.PERMISSION_DENIED.value):
                            self.permission_event.clear() # Limpiar si el permiso es denegado
                            logger.info(f"[{self.vehicle.id}] Permiso denegado.")
                    except json.JSONDecodeError as e:
                        logger.error(f"[{self.vehicle.id}] Error al decodificar JSON: {e} - Data: {msg_bytes}")
                        buffer = b"" 
            except socket.timeout:
                pass # Esto es normal si no hay datos disponibles
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                logger.error(f"[{self.vehicle.id}] Error de conexión en hilo receptor: {e}. Reconectando...")
                self.is_connected = False
                self.conexion()
            except Exception as e:
                logger.error(f"[{self.vehicle.id}] Error inesperado en hilo receptor: {e}")
                self.is_running = False # Detener el hilo si hay un error grave

    def cruzar(self):
        """
        Establece las acciones del vehiculo para cruzar el puente
        """
        cruzando = False
        while self.is_running:
            self.permission_event.clear()
            while self.is_running:
                # Solo enviar REQUEST si no estamos cruzando
                if not cruzando:
                    logger.info(f"[{self.vehicle.id}] Solicitando permiso para cruzar en dirección: {self.vehicle.direccion.value}")
                    if not self._send_raw_message(self.mensaje_template(MessageType.REQUEST.value)):
                        time.sleep(2)
                        continue
                    logger.info(f"[{self.vehicle.id}] Solicitud enviada. Esperando permiso para cruzar...")

                if self.permission_event.wait(timeout=20):
                    with self.lock:
                        last_msg = self.last_server_message

                    # Si el servidor nos notifica que es nuestro turno, debemos enviar un nuevo REQUEST solo si no estamos cruzando
                    if last_msg and last_msg.get('status') == MessageType.PERMISSION_GRANTED.value and last_msg.get('message', '').startswith('Tu turno ha llegado') and not cruzando:
                        logger.info(f"[{self.vehicle.id}] Recibido notificación del scheduler. Enviando REQUEST para cruzar...")
                        if not self._send_raw_message(self.mensaje_template(MessageType.REQUEST.value)):
                            time.sleep(2)
                            continue
                        continue

                    # Si recibimos permiso para cruzar y no estamos cruzando, procedemos
                    if last_msg and last_msg.get('status') == MessageType.PERMISSION_GRANTED.value and not cruzando:
                        logger.info(f"[{self.vehicle.id}] ¡Permiso concedido! Preparándose para cruzar.")
                        cruzando = True
                        self.permission_event.clear()
                        break
                    elif last_msg and last_msg.get('status') == MessageType.STATUS_UPDATE.value and 'ya está en el puente' in last_msg.get('message', ''):
                        # Ignorar mensajes de status si ya estamos cruzando
                        logger.debug(f"[{self.vehicle.id}] Ignorando mensaje de status: {last_msg.get('message')}")
                        continue
                    elif last_msg and last_msg.get('status') == MessageType.PERMISSION_DENIED.value:
                        logger.warning(f"[{self.vehicle.id}] Permiso denegado explícitamente. Esperando notificación del scheduler.")
                        self.permission_event.clear()
                        time.sleep(5)
                        with self.lock:
                            current_last_msg = self.last_server_message
                            if self.permission_event.is_set() and current_last_msg and current_last_msg.get('status') == MessageType.PERMISSION_GRANTED.value and not cruzando:
                                logger.info(f"[{self.vehicle.id}] Recibido permiso del scheduler después de espera pasiva. ¡Procediendo a cruzar!")
                                cruzando = True
                                self.permission_event.clear()
                                break
                            else:
                                logger.info(f"[{self.vehicle.id}] No se recibió permiso del scheduler. Reintentando solicitud.")
                                continue
                    else:
                        logger.warning(f"[{self.vehicle.id}] Recibido un mensaje inesperado o timeout. Reintentando solicitud.")
                        self.permission_event.clear()
                        continue
                else:
                    logger.warning(f"[{self.vehicle.id}] No recibió respuesta a tiempo. Reintentando solicitud...")
                    self.permission_event.clear()
                    continue

            # --- A partir de aquí, el coche TIENE permiso para cruzar ---
            tiempo_cruce = random.uniform(1, self.vehicle.velocidad)
            logger.info(f"[{self.vehicle.id}] Cruzando puente por {tiempo_cruce:.2f} segundos...")
            time.sleep(tiempo_cruce)

            # Notifica fin de cruce
            if not self._send_raw_message(self.mensaje_template(MessageType.END_CROSS.value)):
                logger.error(f"[{self.vehicle.id}] No se pudo notificar el fin del cruce.")

            logger.info(f"[{self.vehicle.id}] Terminó de cruzar. Esperando antes de volver a intentar.")
            cruzando = False

            tiempo_espera = random.uniform(1, self.vehicle.tiempo_retraso)
            logger.info(f"[{self.vehicle.id}] Esperando {tiempo_espera:.2f} segundos antes de volver a cruzar.")
            time.sleep(tiempo_espera)

            self.vehicle.cambiar_direccion() # type: ignore
            logger.info(f"[{self.vehicle.id}] Cambia dirección a: {self.vehicle.direccion.value}")

        logger.info(f"[{self.vehicle.id}] Hilo de cruce finalizado.")


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
            'timestamp': datetime.datetime.now(timezone.utc).isoformat()
        }
        
    def cerrar(self):
        logger.info(f"[{self.vehicle.id}] Cerrando cliente.")
        self.is_running = False # Señal para detener el hilo receptor
        if self.client_socket is not None:
            try:
                self.client_socket.shutdown(socket.SHUT_RDWR) # Intentar un cierre limpio
                self.client_socket.close()
            except Exception as e:
                logger.error(f"[{self.vehicle.id}] Error al cerrar socket: {e}")
            finally:
                self.client_socket = None
        if hasattr(self, 'receiver_thread') and self.receiver_thread.is_alive():
            self.receiver_thread.join(timeout=2) # Esperar un poco a que el hilo termine


if __name__ == "__main__":
    print("=== Cliente de Puente Unidireccional ===")
    id_vehiculo = input("ID del vehículo: ")
    host = "127.0.0.1"
    port = 7777
    
    while True:
        try:
            velocidad = float(input("Velocidad máxima (segundos en puente, ej: 3): "))
            if velocidad <= 0:
                raise ValueError
            break
        except ValueError:
            print("Entrada inválida. Por favor, ingresa un número positivo.")
            
    while True:
        try:
            tiempo_retraso = float(input("Tiempo de retraso tras cruzar (segundos, ej: 2): "))
            if tiempo_retraso <= 0:
                raise ValueError
            break
        except ValueError:
            print("Entrada inválida. Por favor, ingresa un número positivo.")
            
    # Validación de dirección inicial
    while True:
        dir_inicial = input("Dirección inicial [left/right]: ").strip().lower()
        if dir_inicial == "left":
            direccion = Direccion.LEFT
            break
        elif dir_inicial == "right":
            direccion = Direccion.RIGHT
            break
        else:
            print("Dirección inválida. Debe ser 'left' o 'right'.")
    
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
        logger.info("Cerrando cliente por interrupción del usuario...")
    finally:
        client.cerrar()