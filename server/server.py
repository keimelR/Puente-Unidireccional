import socket
import queue
import threading
import json
import sys
import os
import traceback
import time
import datetime
from datetime import timezone

from enum import Enum

# Asegúrate de que las rutas sean correctas para Direccion y MessageType
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model.Direccion import Direccion
from model.MessageType import MessageType

class Server:
    """
        Representacion logica del servidor para manejar las solicitudes del cliente
    """
    def __init__(
        self,
        host = "127.0.0.1",
        port = 7777
    ):
        """
        Constructor de la clase.
        
        Args:
            host: Host del servidor
            port: Puerto de conexion del servidor
            server_socket: Socket del servidor
            running: Atributo para iniciar el servidor
            is_occupied_bridge (bool): Indica la existencia de un vehiculo en el puente
            current_direction (Direccion): Direccion actual de carros que pasan por el puente
            left_traffic (Queue): Trafico en la izquierda del puente
            right_traffic (Queue): Trafico a la derecha del puente
            car_on_bridge: El carro actual que esta cruzando el puente
            active_clients: Diccionario de sockets activos por car_id
            
            bridge_lock (threading): 
            bridge_condition (threading):
        """
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = True
        
        self.cars_on_bridge = 0
        self.cars_on_bridge_ids = []
        self.current_direction = Direccion.NONE
        self.left_traffic: queue.Queue = queue.Queue()
        self.right_traffic: queue.Queue = queue.Queue()
        self.active_clients = {}  # {car_id: client_socket}
        self.next_expected_car_id = None  # Nuevo: para saber quién fue notificado para cruzar
        self.bridge_lock = threading.Lock()
        self.bridge_condition = threading.Condition(self.bridge_lock)

    def start(self):
        """
        Da inicio el server_socket y con ello, el procesamiento del token del cliente
        """
        self.server_socket = socket.socket(socket.AddressFamily.AF_INET, socket.SocketKind.SOCK_STREAM)
        
        try: 
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            print(f"[SERVIDOR] Escuchando en {self.host}:{self.port}")
            
            # Hilo para mantener el puente en funcionamiento (procesar colas)
            threading.Thread(target=self._bridge_scheduler, daemon=True).start()

            while self.running:
                try:
                    client_socket, addr = self.server_socket.accept()
                    print(f"[SERVIDOR] Conexión aceptada de {addr}")
                    # Iniciamos el hilo para el intercambio de solicitudes y respuesta entre el cliente
                    threading.Thread(target=self.handle_client, args=(client_socket, addr), daemon=True).start()
                except OSError as e:
                    if self.running: # Si el servidor se está cerrando, es un error esperado
                        print(f"[ERROR] Error al aceptar conexión: {e}")
                    break  # Servidor cerrado
                except Exception as e:
                    print(f"[ERROR] Error inesperado en el bucle principal del servidor: {e}")
                    traceback.print_exc()
        except Exception as e:
            print(f"[ERROR] Error al iniciar el servidor: {e}")
            traceback.print_exc()

    def stop(self):
        """Cierra el servidor de forma controlada"""
        print("[SERVIDOR] Cerrando servidor...")
        self.running = False
        # Unbind del puerto y cierre del socket del servidor
        if self.server_socket:
            try:
                self.server_socket.shutdown(socket.SHUT_RDWR)
                self.server_socket.close()
            except Exception as e:
                print(f"[ERROR] Error al cerrar socket del servidor: {e}")
        # Cerrar todos los clientes activos
        for car_id, client_socket in list(self.active_clients.items()): # Usar list() para copiar y evitar RuntimeError
            try:
                client_socket.shutdown(socket.SHUT_RDWR)
                client_socket.close()
            except Exception:
                pass
            self.active_clients.pop(car_id, None) # Remover después de intentar cerrar
        print("[SERVIDOR] Servidor cerrado.")

    def template_response(self, status, current_direction: Direccion, message, data = None):
        """
        Template para el envio de respuestas en json
        Args:
            status (MessageType): La condicion actual de la solicitud
            current_direction (Direccion): Direccion actual del puente
            message: Mensaje para el cliente
        
        Returns:
            dict[str, Any]: Representa el Json de respuesta
        """
        response = {
            'status': status,
            'message': message,
            'current_direction': current_direction.value,
            'timestamp': datetime.datetime.now(timezone.utc).isoformat()
        }
        if data:
            response['data'] = data
        return response

    def _send_response(self, client_socket, response_data, car_id=None):
        """Helper para enviar una respuesta a un socket de cliente específico."""
        try:
            message_str = json.dumps(response_data) + "\n"
            client_socket.sendall(message_str.encode('utf-8'))
            print(f"[DEBUG] Enviando a {car_id if car_id else 'desconocido'}: {response_data.get('status', response_data.get('type'))}")
            return True
        except (BrokenPipeError, ConnectionResetError) as e:
            print(f"[WARNING] Cliente {car_id} desconectado o error de pipe al enviar respuesta: {e}")
            return False
        except Exception as e:
            print(f"[ERROR] Error al enviar respuesta a {car_id}: {e}")
            traceback.print_exc()
            return False

    def handle_client(
        self,
        client_socket: socket.socket,
        addr
    ):
        """
        Metodo para el intercambio de mensajes entre el cliente y servidor
        Args:
            client_socket (socket): Socket de nuestro cliente
            Addr: Direccion del socket del cliente
        """
        car_id = None
        try:
            buffer = b""
            client_socket.settimeout(300) # Timeout para inactividad prolongada (5 minutos)
            while self.running:
                data = client_socket.recv(4096) # Aumentar buffer de recepción
                if not data:
                    print(f"[INFO] Cliente {car_id if car_id else addr} cerró la conexión.")
                    break  # El cliente cerró la conexión
                
                buffer += data
                while b"\n" in buffer:
                    msg_bytes, buffer = buffer.split(b"\n", 1)
                    if not msg_bytes.strip():
                        continue # Saltar mensajes vacíos
                    
                    try:
                        message = json.loads(msg_bytes.decode('utf-8'))
                    except json.JSONDecodeError:
                        print(f"[ERROR] No se pudo decodificar JSON del cliente {car_id if car_id else addr}: {msg_bytes.decode(errors='ignore')}")
                        continue # Saltar mensaje malformado y seguir esperando
                    
                    car_id = message.get('id')
                    if car_id:
                        # Si ya hay un socket para este car_id y es diferente, ciérralo y reemplázalo
                        old_socket = self.active_clients.get(car_id)
                        if old_socket and old_socket != client_socket:
                            try:
                                old_socket.shutdown(socket.SHUT_RDWR)
                                old_socket.close()
                            except Exception:
                                pass
                        self.active_clients[car_id] = client_socket
                    
                    self.process_client_request(car_id, message, client_socket)
                    
        except socket.timeout:
            print(f"[INFO] Cliente {car_id if car_id else addr} inactivo por mucho tiempo. Cerrando conexión.")
        except ConnectionResetError:
            print(f"[INFO] Cliente {car_id if car_id else addr} desconectado abruptamente.")
        except Exception as e:
            print(f"[ERROR] Error en el manejo del cliente {car_id if car_id else addr}: {e}")
            traceback.print_exc()
        finally:
            if car_id and car_id in self.active_clients:
                del self.active_clients[car_id]
            try:
                client_socket.close()
            except Exception:
                pass # Ignorar errores al cerrar socket ya cerrado
            self.client_disconnect(client_id=car_id)
            print(f"[INFO] Conexión con cliente {car_id if car_id else addr} cerrada.")

    def process_client_request(self, car_id, message, client_socket):
        car_direction_str = message.get('direction')
        if not car_direction_str:
            self._send_response(client_socket, self.template_response(
                status=MessageType.PERMISSION_DENIED.value,
                current_direction=Direccion.NONE,
                message="Dirección de vehículo no especificada."
            ), car_id)
            return

        try:
            car_direction = Direccion[car_direction_str.upper()]
        except KeyError:
            self._send_response(client_socket, self.template_response(
                status=MessageType.PERMISSION_DENIED.value,
                current_direction=Direccion.NONE,
                message=f"Dirección de vehículo inválida: {car_direction_str}."
            ), car_id)
            return

        msg_type_str = message.get('type')
        if not msg_type_str:
            self._send_response(client_socket, self.template_response(
                status=MessageType.PERMISSION_DENIED.value,
                current_direction=self.current_direction,
                message="Tipo de mensaje no especificado."
            ), car_id)
            return

        try:
            msg_type = MessageType(msg_type_str)
        except ValueError:
            self._send_response(client_socket, self.template_response(
                status=MessageType.PERMISSION_DENIED.value,
                current_direction=self.current_direction,
                message=f"Tipo de mensaje desconocido: {msg_type_str}."
            ), car_id)
            return

        if msg_type == MessageType.REQUEST:
            with self.bridge_lock:
                # Caso 1: El coche ya está en el puente.
                if car_id in self.cars_on_bridge_ids:
                    print(f"[DEBUG] Coche {car_id} envió REQUEST pero ya está en el puente. Dirección: {self.current_direction.value}")
                    self._send_response(client_socket, self.template_response(
                        status=MessageType.STATUS_UPDATE.value,
                        current_direction=self.current_direction,
                        message=f"Coche {car_id} ya está en el puente. Cruzando en dirección {self.current_direction.value}."
                    ), car_id)
                    return
                # Caso 2: El coche no está en el puente y solicita acceso.
                if self.puede_cruzar(car_id, car_direction):
                    self.cars_on_bridge += 1
                    self.cars_on_bridge_ids.append(car_id)
                    self.current_direction = car_direction
                    # Si era el notificado, limpiar el flag
                    if self.next_expected_car_id == car_id:
                        self.next_expected_car_id = None
                    self._send_response(client_socket, self.template_response(
                        status=MessageType.PERMISSION_GRANTED.value,
                        current_direction=self.current_direction,
                        message="Tienes permiso para cruzar. ¡Adelante!"
                    ), car_id)
                    print(f"[PUENTE] Coche {car_id} ingresa directamente al puente. Dirección: {car_direction.value}")
                    self.print_bridge_status()
                else:
                    # Caso 3: El coche no puede cruzar ahora, se encola.
                    queue_added = False
                    if car_direction == Direccion.LEFT:
                        if car_id not in list(self.left_traffic.queue):
                            self.left_traffic.put(car_id)
                            print(f"[COLA] Coche {car_id} encolado a la izquierda. Cola actual: {list(self.left_traffic.queue)}")
                            queue_added = True
                        else:
                            print(f"[COLA] Coche {car_id} ya estaba encolado a la izquierda.")
                    elif car_direction == Direccion.RIGHT:
                        if car_id not in list(self.right_traffic.queue):
                            self.right_traffic.put(car_id)
                            print(f"[COLA] Coche {car_id} encolado a la derecha. Cola actual: {list(self.right_traffic.queue)}")
                            queue_added = True
                        else:
                            print(f"[COLA] Coche {car_id} ya estaba encolado a la derecha.")
                    self._send_response(client_socket, self.template_response(
                        status=MessageType.PERMISSION_DENIED.value,
                        current_direction=self.current_direction,
                        message="Puente ocupado o esperando alternancia. Debes esperar tu turno."
                    ), car_id)
                    self.print_bridge_status()
        elif msg_type == MessageType.END_CROSS:
            with self.bridge_lock:
                if car_id in self.cars_on_bridge_ids:
                    self.cars_on_bridge -= 1
                    self.cars_on_bridge_ids.remove(car_id)
                    print(f"[PUENTE] Coche {car_id} ha salido del puente. Coches restantes: {self.cars_on_bridge}")
                    self._send_response(client_socket, self.template_response(
                        status=MessageType.STATUS_UPDATE.value,
                        current_direction=self.current_direction,
                        message=f"El vehículo {car_id} ha cruzado el puente exitosamente."
                    ), car_id)
                    self.print_bridge_status()
                    self.bridge_condition.notify_all() # Notificar al scheduler del puente
                else:
                    self._send_response(client_socket, self.template_response(
                        status=MessageType.PERMISSION_DENIED.value,
                        current_direction=self.current_direction,
                        message=f"Error: El vehículo {car_id} no estaba registrado en el puente."
                    ), car_id)
                    print(f"[WARNING] Coche {car_id} envió END_CROSS pero no estaba en cars_on_bridge_ids.")
        elif msg_type == MessageType.STATUS_UPDATE:
            self._send_response(client_socket, self.template_response(
                status=MessageType.STATUS_UPDATE.value,
                message="Datos del Puente",
                current_direction=self.current_direction,
                data={
                    "bridge_occupied": self.cars_on_bridge > 0,
                    "cars_on_bridge": self.cars_on_bridge_ids,
                    "left_traffic_size": self.left_traffic.qsize(),
                    "right_traffic_size": self.right_traffic.qsize()
                }
            ), car_id)
        else:
            self._send_response(client_socket, self.template_response(
                status=MessageType.PERMISSION_DENIED.value,
                current_direction=self.current_direction,
                message="Tipo de mensaje desconocido."
            ), car_id)
            
    def _bridge_scheduler(self):
        """
        Hilo que se encarga de decidir qué coche puede cruzar el puente
        cuando este está libre. Se despierta cuando un coche sale del puente.
        """
        while self.running:
            with self.bridge_condition:
                # Esperar hasta que el puente esté desocupado o se notifique un cambio
                while self.cars_on_bridge > 0 and self.running:
                    self.bridge_condition.wait() # Espera pasivamente

                if not self.running:
                    break

                self.next_car()
            time.sleep(0.1) # Pequeña pausa para evitar un bucle de CPU excesivo

    def next_car(self):
        """
        Decide qué coche puede cruzar a continuación, alternando la dirección si hay vehículos esperando
        en la contraria y el puente está libre.
        Esta función ya opera bajo bridge_lock debido a _bridge_scheduler.
        """
        next_car_id = None
        next_direction = Direccion.NONE

        # Alternar o continuar con la misma dirección
        if self.current_direction == Direccion.LEFT:
            if not self.right_traffic.empty():
                next_car_id = self.right_traffic.get()
                next_direction = Direccion.RIGHT
                print(f"[PUENTE] Alternando dirección (LEFT -> RIGHT).")
            elif not self.left_traffic.empty():
                next_car_id = self.left_traffic.get()
                next_direction = Direccion.LEFT
        elif self.current_direction == Direccion.RIGHT:
            if not self.left_traffic.empty():
                next_car_id = self.left_traffic.get()
                next_direction = Direccion.LEFT
                print(f"[PUENTE] Alternando dirección (RIGHT -> LEFT).")
            elif not self.right_traffic.empty():
                next_car_id = self.right_traffic.get()
                next_direction = Direccion.RIGHT
        else: # Direccion.NONE (puente completamente libre al inicio o después de vaciarse ambas colas)
            if not self.left_traffic.empty():
                next_car_id = self.left_traffic.get()
                next_direction = Direccion.LEFT
            elif not self.right_traffic.empty():
                next_car_id = self.right_traffic.get()
                next_direction = Direccion.RIGHT

        if next_car_id:
            self.current_direction = next_direction
            self.next_expected_car_id = next_car_id  # Guardar el coche notificado
            print(f"[PUENTE] Decidiendo: Siguiente coche {next_car_id} de {next_direction.value}. Notificando...")
            self.notify_car_can_cross(next_car_id)
        else:
            self.current_direction = Direccion.NONE
            self.next_expected_car_id = None
            print("[PUENTE] No hay coches esperando en las colas. Puente permanece LIBRE.")
        self.print_bridge_status()

    def notify_car_can_cross(self, car_id):
        """Notifica a un vehículo específico que puede cruzar el puente (desde el scheduler)."""
        with self.bridge_lock:
            client_socket = self.active_clients.get(car_id)
            if client_socket:
                notification = self.template_response(
                    status=MessageType.PERMISSION_GRANTED.value,
                    message='Tu turno ha llegado. ¡Envía un REQUEST para cruzar!',
                    current_direction=self.current_direction
                )
                notification['expected_direction'] = self.current_direction.value
                if self._send_response(client_socket, notification, car_id):
                    print(f"[NOTIFICACIÓN] Enviada a {car_id}: puede cruzar (desde scheduler).")
                else:
                    print(f"[ADVERTENCIA] No se pudo enviar notificación a {car_id}, socket posiblemente cerrado.")
            else:
                print(f"[ADVERTENCIA] No se encontró socket para notificar a {car_id}. Posiblemente se desconectó y fue limpiado.")


    def client_disconnect(self, client_id):
        """
        Remueve un cliente de las colas si se desconecta.
        Esta función se llama cuando el hilo del cliente termina.
        """
        with self.bridge_lock:
            # Remover de cars_on_bridge_ids si estaba cruzando
            if client_id in self.cars_on_bridge_ids:
                self.cars_on_bridge_ids.remove(client_id)
                self.cars_on_bridge -= 1
                print(f"[SERVIDOR] Coche {client_id} se desconectó mientras estaba en el puente. Puente liberado.")
                self.bridge_condition.notify_all() # Notificar que el puente se ha desocupado

            # Reconstruir colas sin el cliente desconectado
            temp_traffic_left = []
            while not self.left_traffic.empty():
                car_in_traffic = self.left_traffic.get_nowait()
                if car_in_traffic != client_id:
                    temp_traffic_left.append(car_in_traffic)
            for car in temp_traffic_left:
                self.left_traffic.put(car)

            temp_traffic_right = []
            while not self.right_traffic.empty():
                car_in_traffic = self.right_traffic.get_nowait()
                if car_in_traffic != client_id:
                    temp_traffic_right.append(car_in_traffic)
            for car in temp_traffic_right:
                self.right_traffic.put(car)
            
            print(f"[LIMPIEZA] Colas actualizadas para {client_id}. Izq: {self.left_traffic.qsize()}, Der: {self.right_traffic.qsize()}")
            self.print_bridge_status()
            # La función _bridge_scheduler se encargará de llamar a next_car si es necesario

    def print_bridge_status(self):
        print(f"--- ESTADO ACTUAL DEL PUENTE ---")
        print(f"  Ocupado: {self.cars_on_bridge > 0} ({self.cars_on_bridge} vehículos)")
        print(f"  Dirección Actual: {self.current_direction.value}")
        print(f"  Vehículos en Puente: {self.cars_on_bridge_ids}")
        print(f"  Cola Izquierda: {list(self.left_traffic.queue)}")
        print(f"  Cola Derecha: {list(self.right_traffic.queue)}")
        print(f"---------------------------------")

    def puede_cruzar(self, car_id, car_direction):
        # Si el puente está libre y es el notificado (o no hay notificado), puede cruzar SIEMPRE
        if self.cars_on_bridge == 0:
            if self.next_expected_car_id is None or self.next_expected_car_id == car_id:
                return True
            return False
        # Si el puente está ocupado, solo puede cruzar si la dirección coincide y no hay coches esperando en la opuesta
        if self.current_direction == car_direction:
            if car_direction == Direccion.LEFT and self.right_traffic.qsize() > 0:
                return False
            if car_direction == Direccion.RIGHT and self.left_traffic.qsize() > 0:
                return False
            return True
        return False
    
    # La alternancia se gestiona ahora en next_car y el scheduler

if __name__ == "__main__":
    print("[SERVIDOR] Iniciando servidor de puente unidireccional...")
    server = Server()
    try:
        server.start()
    except KeyboardInterrupt:
        print("[SERVIDOR] Interrupción por usuario.")
    finally:
        server.stop()