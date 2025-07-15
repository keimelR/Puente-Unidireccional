import pygame
import pygame_gui
import threading
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from client.client import Client
from model.Direccion import Direccion

carro_anim_start_time = 0
carro_anim_total_time = 1
carro_anim_in_progress = False

# Estado simulado del puente y del vehículo
bridge_state = {
    "ocupado": False,
    "direccion": "LEFT",
    "en_puente": [],
    "cola_izquierda": [],
    "cola_derecha": []
}
# Estado visual del vehículo
carro_cruzando = False
carro_pos = 0
carro_dir = "LEFT"  # o "RIGHT"
carro_id = None

import time

def actualizar_estado_puente():
    global carro_cruzando, carro_dir, carro_id, carro_pos
    global carro_anim_start_time, carro_anim_total_time, carro_anim_in_progress

    if cliente_iniciado and cliente_obj is not None:
        cliente_obj.actualizar_estado_puente(bridge_state)

    # Solo animar si el carro en el puente es el de este cliente
    mi_id = cliente_obj.vehicle.id if cliente_obj else None
    en_puente = bridge_state["en_puente"]
    if en_puente and mi_id in en_puente:
        if not carro_cruzando:
            # El carro acaba de empezar a cruzar
            carro_anim_start_time = time.time()
            carro_anim_total_time = cliente_obj.vehicle.velocidad
            carro_anim_in_progress = True
        carro_cruzando = True
        carro_id = mi_id
        carro_dir = bridge_state["direccion"]
    else:
        carro_cruzando = False
        carro_id = None
        carro_anim_in_progress = False

pygame.init()
pygame.display.set_caption("Cliente Puente Unidireccional")
window_size = (800, 600)  # Aumenta la resolución
window_surface = pygame.display.set_mode(window_size)
manager = pygame_gui.UIManager(window_size)

# Etiquetas para los campos
label_id = pygame_gui.elements.UILabel(relative_rect=pygame.Rect((20, 0), (100, 20)), text="ID Vehículo", manager=manager)
label_vel = pygame_gui.elements.UILabel(relative_rect=pygame.Rect((140, 0), (100, 20)), text="Velocidad", manager=manager)
label_delay = pygame_gui.elements.UILabel(relative_rect=pygame.Rect((260, 0), (100, 20)), text="Retraso", manager=manager)
label_dir = pygame_gui.elements.UILabel(relative_rect=pygame.Rect((380, 0), (100, 20)), text="Dirección", manager=manager)

# Elementos de UI para parámetros del cliente
input_id = pygame_gui.elements.UITextEntryLine(relative_rect=pygame.Rect((20, 20), (100, 30)), manager=manager)
input_id.set_text("1")
input_vel = pygame_gui.elements.UITextEntryLine(relative_rect=pygame.Rect((140, 20), (100, 30)), manager=manager)
input_vel.set_text("5")
input_delay = pygame_gui.elements.UITextEntryLine(relative_rect=pygame.Rect((260, 20), (100, 30)), manager=manager)
input_delay.set_text("3")
input_dir = pygame_gui.elements.UIDropDownMenu(['LEFT', 'RIGHT'], 'LEFT', pygame.Rect((380, 20), (100, 30)), manager)

start_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((500, 20), (80, 30)), text='Iniciar', manager=manager)

# Panel de estado del puente con mayor área
status_panel = pygame_gui.elements.UITextBox(
    html_text="Estado del puente aparecerá aquí.",
    relative_rect=pygame.Rect((20, 70), (760, 200)),  # Más ancho y alto
    manager=manager,
    object_id="#estado_puente"
)

clock = pygame.time.Clock()
is_running = True
cliente_iniciado = False
cliente_thread = None
cliente_obj = None

def render_estado():
    html = f"""
    <b>Ocupado:</b> {"Sí" if bridge_state["ocupado"] else "No"}<br>
    <b>Dirección Actual:</b> {bridge_state["direccion"]}<br>
    <b>Vehículos en Puente:</b> {bridge_state["en_puente"]}<br>
    <b>Cola Izquierda:</b> {bridge_state["cola_izquierda"]}<br>
    <b>Cola Derecha:</b> {bridge_state["cola_derecha"]}<br>
    """
    status_panel.set_text(html)

def iniciar_cliente():
    global cliente_obj
    id_vehiculo = input_id.get_text()
    try:
        velocidad = float(input_vel.get_text())
        tiempo_retraso = float(input_delay.get_text())
    except ValueError:
        print("Velocidad y retraso deben ser números.")
        return
    direccion = Direccion.LEFT if input_dir.selected_option == "LEFT" else Direccion.RIGHT
    cliente_obj = Client(
        id=id_vehiculo,
        host="127.0.0.1",
        port=7777,
        velocidad=velocidad,
        tiempo_retraso=tiempo_retraso,
        direccion=direccion
    )
    t = threading.Thread(target=cliente_obj.cruzar, daemon=True)
    t.start()
    return t

puente_rect = pygame.Rect(200, 350, 400, 60)  # Más grande y centrado
carro_size = 40  # Más grande
carro_speed = 3  # píxeles por frame

while is_running:
    time_delta = clock.tick(30) / 1000.0
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            is_running = False
        if event.type == pygame_gui.UI_BUTTON_PRESSED and event.ui_element == start_button and not cliente_iniciado:
            cliente_thread = iniciar_cliente()
            cliente_iniciado = True
        manager.process_events(event)

    # Actualiza el estado del puente y del carro
    actualizar_estado_puente()
    render_estado()

    # --- Animación del carro cruzando el puente ---
    if carro_anim_in_progress and carro_cruzando:
        elapsed = time.time() - carro_anim_start_time
        progress = min(elapsed / carro_anim_total_time, 1.0)
        if carro_dir == "LEFT":
            start_x = puente_rect.left
            end_x = puente_rect.right - carro_size
            carro_pos = start_x + (end_x - start_x) * progress
        else:
            start_x = puente_rect.right - carro_size
            end_x = puente_rect.left
            carro_pos = start_x - (start_x - end_x) * progress
        if progress >= 1.0:
            carro_anim_in_progress = False
    else:
        # Posición inicial según dirección
        carro_pos = puente_rect.left if carro_dir == "LEFT" else puente_rect.right - carro_size

    manager.update(time_delta)
    window_surface.fill((30, 30, 30))
    manager.draw_ui(window_surface)

    # Dibuja el puente
    pygame.draw.rect(window_surface, (120, 120, 120), puente_rect)
    # Dibuja el carro si está cruzando
    if carro_cruzando:
        pygame.draw.rect(window_surface, (0, 200, 0), (carro_pos, puente_rect.top + 5, carro_size, carro_size))
        # Opcional: muestra el ID del carro
        font = pygame.font.SysFont(None, 24)
        text = font.render(str(carro_id), True, (255, 255, 255))
        window_surface.blit(text, (carro_pos + 5, puente_rect.top + 10))

    pygame.display.update()

if cliente_obj:
    cliente_obj.cerrar()

pygame.quit()