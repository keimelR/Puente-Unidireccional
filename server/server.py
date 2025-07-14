import socket
import queue
import threading
import json
import sys
import os
import traceback
from enum import Enum
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model.Direccion import Direccion
from model.MessageType import MessageType

class MessageStatus(str, Enum):
    """Estados de respuesta del servidor"""
    EXITOSO = "Exitoso"
    EN_ESPERA = "En espera"
    ERROR = "Error"
    INFO = "Info"

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
        
        self.is_occupied_bridge: bool = False
        self.current_direction = Direccion.NONE
        self.left_traffic: queue.Queue = queue.Queue()
        self.right_traffic: queue.Queue = queue.Queue()
        self.car_on_bridge = None 
        self.active_clients = {}  # {car_id: client_socket}
        
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
            
            while self.running:
                try:
                    client_socket, addr = self.server_socket.accept()
                    # Iniciamos el hilo para el intercambio de solicitudes y respuesta entre el cliente
                    threading.Thread(target=self.msg_client, args=(client_socket, addr), daemon=True).start()
                except OSError:
                    break  # Servidor cerrado
        except Exception as e:
            print(f"[ERROR] Error en servidor: {e}")
            traceback.print_exc()

    def stop(self):
        """Cierra el servidor de forma controlada"""
        print("[SERVIDOR] Cerrando servidor...")
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        # Cerrar todos los clientes activos
        for car_id, client_socket in self.active_clients.items():
            try:
                client_socket.close()
            except:
                pass
        self.active_clients.clear()

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
            'current_direction': current_direction.value
        }
        if data:
            response['data'] = data
        return response

    def msg_client(
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
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break  # El cliente cerró la conexión
                buffer += data
                while b"\n" in buffer:
                    msg_bytes, buffer = buffer.split(b"\n", 1)
                    if not msg_bytes:
                        continue
                    message = json.loads(msg_bytes.decode())
                    car_id = message.get('id')
                    
                    # Registrar cliente activo
                    if car_id:
                        self.active_clients[car_id] = client_socket
                    
                    response = self.process_message(message)
                    print(f"[DEBUG] Enviando respuesta a {car_id}: {response}")
                    client_socket.sendall((json.dumps(response) + "\n").encode())
                    # Si fue END_CROSS, ejecutar next_car() aquí
                    if message.get('type') == MessageType.END_CROSS.value:
                        self.next_car()
        except Exception as e:
            print(f"[ERROR] Error en cliente {car_id}: {e}")
            traceback.print_exc()
        finally:
            client_socket.close()
            try:
                if car_id:
                    # Remover de clientes activos
                    self.active_clients.pop(car_id, None)
                    self.client_disconnect(client_id=car_id)
            except Exception as e:
                print(f"[DEBUG] Error en client_disconnect: {e}")
            
    def process_message(self, message):
        """
        Metodo para procesar los tokens del cliente
        
        Args:
            message: El token del cliente
        """
        
        # Identificador unico del carro
        car_id = message.get('id')
        
        # Validación de car_direction
        car_direction_str = message.get('direction')
        if not car_direction_str:
            return self.template_response(
                status = MessageStatus.ERROR, 
                current_direction = Direccion.NONE, 
                message = "Dirección de vehículo no especificada."
            )
        try:
            car_direction = Direccion[car_direction_str.upper()]
        except KeyError:
            return self.template_response(
                status = MessageStatus.ERROR, 
                current_direction = Direccion.NONE, 
                message = f"Dirección de vehículo inválida: {car_direction_str}."
            )

        # Validación de msg_type
        msg_type_str = message.get('type')
        if not msg_type_str:
            return self.template_response(
                status = MessageStatus.ERROR, 
                current_direction = self.current_direction, 
                message = "Tipo de mensaje no especificado."
            )
        try:
            msg_type = MessageType(msg_type_str)
        except ValueError:
            return self.template_response(
                status = MessageStatus.ERROR, 
                current_direction = self.current_direction, 
                message = f"Tipo de mensaje desconocido: {msg_type_str}."
            )

        with self.bridge_condition:
            if msg_type == MessageType.REQUEST:
                # Permitir cruce en cualquier dirección si el puente está libre
                if not self.is_occupied_bridge:
                    self.is_occupied_bridge = True
                    self.current_direction = car_direction
                    self.car_on_bridge = car_id
                    print(f"El vehiculo {car_id} está cruzando.")
                    self.print_bridge_status()
                    return self.template_response(
                        status = MessageStatus.EXITOSO,
                        current_direction = car_direction,
                        message = 'El vehiculo esta atravesando el puente' 
                    )
                # Si el puente está ocupado y la dirección es contraria, poner en cola
                if self.is_occupied_bridge and self.current_direction != car_direction:
                    if car_direction == Direccion.LEFT:
                        self.left_traffic.put(car_id)
                        print(f"Insertado en la cola izquierda")
                    elif car_direction == Direccion.RIGHT:
                        self.right_traffic.put(car_id)
                        print(f"Insertado en la cola derecha")
                    self.print_bridge_status()
                    return self.template_response(
                        status = MessageStatus.EN_ESPERA,
                        current_direction = self.current_direction,  # Usar la dirección real del puente
                        message = 'Vehiculos circulando desde la direccion contraria' 
                    )
                # Si el puente está ocupado y la dirección es la misma, pero hay coches esperando en la contraria, poner en cola
                if self.is_occupied_bridge and self.current_direction == car_direction:
                    if (car_direction == Direccion.LEFT and not self.right_traffic.empty()) or \
                       (car_direction == Direccion.RIGHT and not self.left_traffic.empty()):
                        if car_direction == Direccion.LEFT:
                            self.left_traffic.put(car_id)
                            print(f"[{car_id}] Encolado en IZQUIERDA (cediendo al tráfico DERECHO).")
                        else:
                            self.right_traffic.put(car_id)
                            print(f"[{car_id}] Encolado en DERECHA (cediendo al tráfico IZQUIERDO).")
                        self.print_bridge_status()
                        return self.template_response(
                            status = MessageStatus.EN_ESPERA,
                            current_direction = self.current_direction,  # Usar la dirección real del puente
                            message = "Hay vehículos esperando en la dirección contraria. Esperando turno."
                        )
                # Si llegamos aquí, el coche puede pasar (misma dirección y sin conflicto)
                self.is_occupied_bridge = True
                self.current_direction = car_direction
                self.car_on_bridge = car_id
                print(f"El vehiculo {car_id} está cruzando.")
                self.print_bridge_status()
                return self.template_response(
                    status = MessageStatus.EXITOSO,
                    current_direction = self.current_direction,  # Usar la dirección real del puente
                    message = 'El vehiculo esta atravesando el puente' 
                )
            elif msg_type == MessageType.END_CROSS:
                print(f"[DEBUG] END_CROSS recibido: car_id={car_id}, car_on_bridge={self.car_on_bridge}")
                if self.is_occupied_bridge and self.car_on_bridge == car_id:
                    # Liberar el puente correctamente
                    self.is_occupied_bridge = False
                    self.car_on_bridge = None
                    print(f"El vehiculo {car_id} ha cruzado y liberado el puente.")
                    self.print_bridge_status()
                    self.bridge_condition.notify_all()
                    print(f"[DEBUG] Retornando respuesta exitosa END_CROSS para {car_id}")
                    response = self.template_response(
                        status = MessageStatus.EXITOSO,
                        current_direction = self.current_direction,  # Usar la dirección real del puente
                        message = f"El vehiculo {car_id} ha cruzado el puente"
                    )
                    # Quitamos self.next_car() de aquí
                    return response
                else:
                    if not self.is_occupied_bridge and self.car_on_bridge is None:
                        print(f"[DEBUG] END_CROSS tolerante: puente ya libre, id={car_id}")
                        print(f"[DEBUG] Retornando respuesta exitosa tolerante END_CROSS para {car_id}")
                        return self.template_response(
                            status = MessageStatus.EXITOSO,
                            current_direction = self.current_direction,  # Usar la dirección real del puente
                            message = f"El vehiculo {car_id} ha cruzado el puente (tolerancia)"
                        )
                    print(f"[DEBUG] Retornando respuesta de error END_CROSS para {car_id}")
                    return self.template_response(
                        status = MessageStatus.ERROR,
                        current_direction = self.current_direction,  # Usar la dirección real del puente
                        message = f'Hubo un error al cruzar por el puente por el vehiculo {car_id} (no coincide id o puente no ocupado)'
                    )
            elif msg_type == MessageType.STATUS:
                self.print_bridge_status()
                return self.template_response(
                    status = MessageStatus.INFO,
                    message = "Datos del Puente",
                    current_direction = self.current_direction,
                    data = {
                        "bridge_occupied": self.is_occupied_bridge,
                        "car_on_bridge": self.car_on_bridge,
                        "left_traffic_size": self.left_traffic.qsize(),
                        "right_traffic_size": self.right_traffic.qsize()
                    }
                )
            else:
                return self.template_response(
                    status = MessageStatus.ERROR,
                    current_direction = self.current_direction,
                    message = "Tipo de mensaje desconocido."
                )
            
    def next_car(self):
        """Decide qué coche puede cruzar a continuación, alternando la dirección si hay vehículos esperando en la contraria."""
        with self.bridge_lock:
            if self.is_occupied_bridge:
                return  # El puente sigue ocupado

            next_car_id = None
            next_direction = Direccion.NONE

            # Prioridad 1: Si hay vehículos esperando en la dirección contraria, alterna
            if self.current_direction == Direccion.LEFT and not self.right_traffic.empty():
                next_car_id = self.right_traffic.get()
                next_direction = Direccion.RIGHT
                print(f"[PUENTE] Alternando dirección: {self.current_direction.value} -> {next_direction.value}")
            elif self.current_direction == Direccion.RIGHT and not self.left_traffic.empty():
                next_car_id = self.left_traffic.get()
                next_direction = Direccion.LEFT
                print(f"[PUENTE] Alternando dirección: {self.current_direction.value} -> {next_direction.value}")
            # Prioridad 2: Si no hay vehículos en la dirección contraria, continúa con la dirección actual
            elif self.current_direction == Direccion.LEFT and not self.left_traffic.empty():
                next_car_id = self.left_traffic.get()
                next_direction = Direccion.LEFT
            elif self.current_direction == Direccion.RIGHT and not self.right_traffic.empty():
                next_car_id = self.right_traffic.get()
                next_direction = Direccion.RIGHT
            # Prioridad 3: Si el puente no tiene dirección establecida, da paso a cualquier lado
            elif self.current_direction == Direccion.NONE:
                if not self.left_traffic.empty():
                    next_car_id = self.left_traffic.get()
                    next_direction = Direccion.LEFT
                elif not self.right_traffic.empty():
                    next_car_id = self.right_traffic.get()
                    next_direction = Direccion.RIGHT

            if next_car_id:
                self.is_occupied_bridge = True
                self.current_direction = next_direction
                self.car_on_bridge = next_car_id
                print(f"[PUENTE] Siguiente coche {next_car_id} cruza en dirección: {next_direction.value}")
                self.print_bridge_status()
                
                # Notificar automáticamente al siguiente vehículo que puede cruzar
                self.notify_car_can_cross(next_car_id)
            else:
                # Si no hay vehículos esperando, liberar completamente el puente
                self.current_direction = Direccion.NONE
                print("[PUENTE] No hay coches esperando. Puente permanece LIBRE.")
                self.print_bridge_status()

    def notify_car_can_cross(self, car_id):
        """Notifica a un vehículo específico que puede cruzar el puente"""
        try:
            if car_id in self.active_clients:
                client_socket = self.active_clients[car_id]
                notification = {
                    'type': 'PERMIT_CROSS',
                    'status': MessageStatus.EXITOSO.value,
                    'message': 'Puedes cruzar el puente ahora',
                    'current_direction': self.current_direction.value
                }
                client_socket.sendall((json.dumps(notification) + "\n").encode())
                print(f"[NOTIFICACIÓN] Enviada a {car_id}: puede cruzar")
        except Exception as e:
            print(f"[ERROR] No se pudo notificar a {car_id}: {e}")

    def client_disconnect(self, client_id):
        """
        Remueve un cliente de las colas si se desconecta
        """
        with self.bridge_lock:
            # Quitar de las colas, si estaba ahí (get_nowait si no queremos bloquear)
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

    def print_bridge_status(self):
        print(f"[ESTADO PUENTE] Ocupado: {self.is_occupied_bridge} | Dirección: {self.current_direction.value} | En puente: {self.car_on_bridge}")
        print(f"[COLAS] Izquierda: {list(self.left_traffic.queue)} | Derecha: {list(self.right_traffic.queue)}")

if __name__ == "__main__":
    print("[SERVIDOR] Iniciando servidor de puente unidireccional...")
    server = Server()
    server.start()