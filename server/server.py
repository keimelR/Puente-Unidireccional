import socket
import queue
import threading
import json
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
            
            bridge_lock (threading): 
            bridge_condition (threading):
        """
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = True
        
        self.is_occupied_bridge: bool = False
        self.current_direction = Direccion.NONE
        self.left_traffic: queue = queue.Queue()
        self.right_traffic: queue = queue.Queue()
        self.car_on_bridge = None 
        
        self.bridge_lock = threading.Lock()
        self.bridge_condition = threading.Condition(self.bridge_lock)

    def start(self):
        """
        Da inicio el server_socket y con ello, el procesamiento del token del cliente
        """
        self.server_socket = socket.socket(socket.AddressFamily.AF_INET, socket.SocketKind.SOCK_STREAM)
        
        try: 
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen()
            
            while(self.running):
                client_socket, addr = self.server_socket.accept()
                
                # Iniciamos el hilo para el intercambio de solicitudes y respuesta entre el cliente
                threading.Thread(target=self.msg_client, args=(client_socket, addr)).start()
        except Exception as e:
            print(e)

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
        try:
            client_id = f"{addr[0]}:{addr[1]}"    
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break
                message = json.loads(data.decode())
                response = self.process_message(message)
                client_socket.send(json.dumps(response).encode())
        except Exception as e:
            print(e)
        finally:
            client_socket.close()
            self.client_disconnect(client_id = client_id)
            
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
                status = "Error", 
                current_direction = Direccion.NONE, 
                message = "Dirección de vehículo no especificada."
            )
        try:
            car_direction = Direccion[car_direction_str.upper()]
        except KeyError:
            return self.template_response(
                status = "Error", 
                current_direction = Direccion.NONE, 
                message = f"Dirección de vehículo inválida: {car_direction_str}."
            )

        # Validación de msg_type
        msg_type_str = message.get('type')
        if not msg_type_str:
            return self.template_response(
                status = "Error", 
                current_direction = self.current_direction, 
                message = "Tipo de mensaje no especificado."
            )
        try:
            msg_type = MessageType[msg_type_str.upper()]
        except KeyError:
            return self.template_response(
                status = "Error", 
                current_direction = self.current_direction, 
                message = f"Tipo de mensaje desconocido: {msg_type_str}."
            )

        with self.bridge_condition:
            # En caso de que la solicitud sea para ingresar al puente
            if msg_type == MessageType.REQUEST:
                if self.is_occupied_bridge and self.current_direction != car_direction:
                    
                    # Se inserta en el trafico correspondiente
                    if car_direction == Direccion.LEFT:
                        self.left_traffic.put(car_id)
                        print(f"Insertado en la cola izquierda")
                    elif car_direction == Direccion.RIGHT:
                        self.right_traffic.put(car_id)
                        print(f"Insertado en la cola derecha")

                    # Respuesta para el cliente
                    return self.template_response(
                        status = 'En espera',
                        current_direction = car_direction,
                        message = 'Vehiculos circulando desde la direccion contraria' 
                    )
                
                
                if not self.is_occupied_bridge or (self.is_occupied_bridge and self.current_direction == car_direction):
                    if self.is_occupied_bridge and self.current_direction == car_direction:
                        # Si el puente está ocupado en la misma dirección, pero hay coches esperando en la direccion opuesta. Entonces, este coche actual debe esperar en la cola
                        if (car_direction == Direccion.LEFT and not self.right_traffic.empty()) or \
                        (car_direction == Direccion.RIGHT and not self.left_traffic.empty()):

                            # Insertamos en el trafico correspondiente
                            if car_direction == Direccion.LEFT:
                                self.left_traffic.put(car_id)
                                print(f"[{car_id}] Encolado en IZQUIERDA (cediendo al tráfico DERECHO).")
                            else:
                                self.right_traffic.put(car_id)
                                print(f"[{car_id}] Encolado en DERECHA (cediendo al tráfico IZQUIERDO).")

                            # Respuesta para el cliente
                            return self.template_response(
                                status = 'En espera',
                                current_direction = car_direction, # O el current_direction del puente
                                message = "Hay vehículos esperando en la dirección contraria. Esperando turno."
                            )

                    # Si llegamos aquí, el coche puede pasar
                    self.is_occupied_bridge = True
                    self.current_direction = car_direction
                    self.car_on_bridge = car_id 
                    
                    print(f"El vehiculo {car_id} está cruzando.")
                    
                    # Respuesta para el cliente
                    return self.template_response(
                        status = 'Exitoso',
                        car_direction = car_direction,
                        message = 'El vehiculo esta atravesando el puente' 
                    )
            
            # En caso que el cliente haya llegado al final del puente
            elif msg_type == MessageType.END_CROSS:
                if self.is_occupied_bridge and self.car_on_bridge == car_id:
                    # Determinamos que el puente no esta ocupado
                    self.is_occupied_bridge = False
                    
                    # Eliminamos el carro que paso por el puente
                    self.car_on_bridge = None 
                    print(f"El vehiculo {car_id} ha cruzado y liberado el puente.")
                
                    # Activa los subprocesos que esperaban
                    self.bridge_condition.notify_all()
                    
                    # Preparamos el siguiente vehiculo para el puente
                    self.next_car()
                    
                    # Respuesta para el cliente
                    return self.template_response(
                        status = 'Exitoso',
                        car_direction = car_direction,
                        message = f"El vehiculo {car_id} ha cruzado el puente"
                    )
                else:
                    # Respuesta para el cliente
                    return self.template_response(
                        status = 'Error',
                        car_direction = car_direction,
                        message = f'Hubo un error al cruzar por el puente por el vehiculo {car_id}'
                    )
            
            # En caso de querer observar el status
            elif msg_type == MessageType.STATUS:
                # Respuesta para el server
                return self.template_response(
                    status = "Info",
                    message = "Datos del Puente",
                    current_direction = self.current_direction.value,
                    data = {
                        "bridge_occupied": self.is_occupied_bridge,
                        "car_on_bridge": self.car_on_bridge,
                        "left_traffic_size": self.left_traffic.qsize(),
                        "right_traffic_size": self.right_traffic.qsize()
                    }
                )
            else:
                # Respuesta para el server
                return self.template_response(
                    status = "Error",
                    message = "Tipo de mensaje desconocido."
                )
            
    def next_car(self):
        """Decide qué coche puede cruzar a continuación."""
        
        with self.bridge_lock: 
            if self.is_occupied_bridge:
                return # El puente sigue ocupado

            next_car_id = None
            next_direction = Direccion.NONE

            # Lógica para alternar direcciones o dar prioridad
            if self.current_direction == Direccion.LEFT:
                if not self.left_traffic.empty():
                    next_car_id = self.left_traffic.get()
                    next_direction = Direccion.LEFT
                elif not self.right_traffic.empty():
                    next_car_id = self.right_traffic.get()
                    next_direction = Direccion.RIGHT
            elif self.current_direction == Direccion.RIGHT:
                if not self.right_traffic.empty():
                    next_car_id = self.right_traffic.get()
                    next_direction = Direccion.RIGHT
                elif not self.left_traffic.empty():
                    next_car_id = self.left_traffic.get()
                    next_direction = Direccion.LEFT
            else:
                if not self.left_traffic.empty():
                    next_car_id = self.left_traffic.get()
                    next_direction = Direccion.LEFT
                elif not self.right_traffic.empty():
                    next_car_id = self.right_traffic.get()
                    next_direction = Direccion.RIGHT

            # Si ya hemos seleccionado el siguiente vehiculo
            if next_car_id:
                # Marcamos como ocupado el puente
                self.is_occupied_bridge = True
                
                # Marcamos la direccion del trafico del puente
                self.current_direction = next_direction
                
                # Marcamos el vehiculo que esta circulando el puente
                self.car_on_bridge = next_car_id
                     
                print(f"[PUENTE] Siguiente coche {next_car_id} cruza en dirección: {next_direction.value}.")

            else:
                # El puente queda sin dirección activa
                self.current_direction = Direccion.NONE 
                print("[PUENTE] No hay coches esperando. Puente permanece LIBRE.")

    def client_disconnect(self, client_id):
        """
        Remueve un cliente de las colas si se desconecta
        """
        with self.bridge_lock:
            if self.car_on_bridge == client_id:
                self.is_occupied_bridge = False
                self.current_direction = Direccion.NONE
                self.car_on_bridge = None
                print(f"[LIMPIEZA] Coche {client_id} removido del puente por desconexión.")
                
                # Notificar si el puente se libera
                self.bridge_condition.notify_all() 
                
                # Intentar dar paso a otro
                self.next_car() 

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