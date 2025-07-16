# Sistema distribuidon en proyecto: Puente de una via.

La idea del proyecto del sistema distribuido en el puente de una via es proporcionar una solución para que los vehículos que vienen de diferentes direcciones crucen el puente de una via. Desarrollar un proceso de servidor para gestionar el uso del puente. Supongamos que los automóviles son procesos de cliente que pueden conectarse de forma remota al servidor en cualquier momento. En su programa de simulación, haga que nuevos autos se unan a la sesión de forma remota y cada auto intente cruzar el puente repetidamente. Deben pasar una cantidad de tiempo aleatoria en el puente y deben esperar un período de tiempo aleatorio antes de volver a cruzar. Cada cliente de automóvil puede especificar algunos parámetros como su velocidad, tiempo promedio de retraso después de cruzar, dirección de rumbo inicial, etc. Cada cliente debería obtener una interfaz gráfica que muestre el estado actual de la utilización del puente.

Su entrega es un cuaderno electronico con la siguiente informacion:
1. Diseno de la aplicacion que contenga:
    * Casos de Usos
    * Diagramas de interaccion con los mensajes de intercambio entre nodos
    * Arquitecturas, incluya los Protocolos usado. 
2. Codigo en detalle con su explicacion. Incluya videos con explicacion de cada pieza del codigo
3. Ejecucion. Incluya videos donde se muestre  la ejecucion y salida con los monitores y demas graficos ademas de videos de la simulacion.

**Requerimientos**: puede seleccionar el lenguaje de programacion de su preferencia.
Debe definir un servidor y varios clientes. La cantidad de clientes  se genera aleatoriamente.
Debe especificar los protocolos de la capa de transporte y de la capa de aplicacion que se usen

Evaluacion: 30 puntos
* 15 puntos documento del diseno
* 15 puntos  en implementacion ajustada a requerimientos

# ¿Cómo correr este proyecto?

Sigue estos pasos para ejecutar el sistema distribuido del puente unidireccional:

1. **Clona o descarga este repositorio** en tu máquina local.

2. **Instala las dependencias** necesarias:
   - Asegúrate de tener Python 3.8 o superior instalado.
   - Instala los paquetes requeridos ejecutando en la terminal (en la raíz del proyecto):
     ```bash
     pip install -r requirements.txt
     ```
   - Si usas Linux o Anaconda y no tienes Tkinter, instálalo manualmente:
     - En Ubuntu/Debian: `sudo apt-get install python3-tk`
     - En Anaconda: `conda install tk`

3. **Inicia el servidor**:
   - Ve a la carpeta `server` y ejecuta:
     ```bash
       python server\server.py
     ```

4. **Inicia uno o varios clientes**:
   - Ve a la carpeta `presentation` y ejecuta:
     ```bash
     python presentation\main.py
     ```
   - Se abrirá una interfaz gráfica donde puedes configurar los parámetros del vehículo y conectarte al servidor.
   - Puedes abrir varias instancias del cliente para simular varios vehículos.

5. **Detén el sistema**:
   - Para detener el servidor o los clientes, simplemente cierra la ventana o usa `Ctrl+C` en la terminal.

**Notas:**
- El servidor debe estar corriendo antes de iniciar cualquier cliente.
- Si tienes problemas con la interfaz gráfica, revisa que `pygame` y `pygame_gui` estén correctamente instalados.
- El sistema está diseñado para ejecutarse en Windows, pero puede funcionar en Linux/Mac con los paquetes adecuados.