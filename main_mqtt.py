"""
OBJETIVO:     Script principal de comunicación del sistema SleepBear.
              Coordina dos canales en paralelo:
              • MQTT     → publica telemetría de sensores en tiempo real
                           y recibe comandos para los actuadores desde
                           la app web.
              • Firebase → persiste historial de sensores y permite
                           controlar actuadores desde la app web cuando
                           no hay conexión MQTT activa.
              Toda la lógica de hardware se delega exclusivamente a la
              HAL (dispositivos.py). Este módulo no accede al hardware.
INTEGRANTES:  Jacziry Berenice Aragón Guerrero
              Juan José Cortes Íñiguez
PROYECTO:     SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

from dispositivos import CajaDeSensores, CajaDeActuadores
from umqtt.simple import MQTTClient
import ufirebase as firebase
import machine, ubinascii, network, time, gc


# =============================================================================
#  CONFIGURACIÓN — ajustar antes de flashear
# =============================================================================

# ── WiFi ─────────────────────────────────────────────────────────────────────
SSID_WIFI  = "TU_RED_WIFI"
CLAVE_WIFI = "TU_CLAVE_WIFI"

# ── MQTT ─────────────────────────────────────────────────────────────────────
SERVIDOR_MQTT = "broker.hivemq.com"
PUERTO_MQTT   = 1883
ID_CLIENTE    = ubinascii.hexlify(machine.unique_id())
USUARIO_MQTT  = ""
CLAVE_MQTT    = ""

# ── Firebase Realtime Database ────────────────────────────────────────────────
# Reemplazar con la URL del proyecto SleepBear en Firebase Console
FIREBASE_URL  = "https://TU-PROYECTO-default-rtdb.firebaseio.com/"

# ── Tiempos ──────────────────────────────────────────────────────────────────
INTERVALO_MQTT     = 5000    # ms entre publicaciones MQTT de sensores
INTERVALO_FIREBASE = 15000   # ms entre sincronizaciones con Firebase


# =============================================================================
#  TABLA DE TÓPICOS MQTT — SleepBear
# =============================================================================
#
#  PUBLICACIONES (ESP32 → App Web vía MQTT)
#  ┌─────────────────────────────────────────┬─────────────────────────────┐
#  │ Tópico                                  │ Descripción                 │
#  ├─────────────────────────────────────────┼─────────────────────────────┤
#  │ sleepbear/sensores/temp_bebe            │ Temperatura bebé en °C      │
#  │ sleepbear/sensores/temp_cuarto          │ Temperatura cuarto en °C    │
#  │ sleepbear/sensores/humedad              │ Humedad cuarto en %         │
#  │ sleepbear/sensores/nivel_luz            │ Nivel de luz 0–100%         │
#  │ sleepbear/sensores/nivel_sonido         │ Nivel de sonido 0–100%      │
#  │ sleepbear/alertas/fiebre                │ "SI" / "NO"                 │
#  │ sleepbear/alertas/cuarto_caliente       │ "SI" / "NO"                 │
#  │ sleepbear/alertas/llanto                │ "SI" / "NO"                 │
#  │ sleepbear/alertas/modo_noche            │ "SI" / "NO"                 │
#  └─────────────────────────────────────────┴─────────────────────────────┘
#
#  SUSCRIPCIONES (App Web → ESP32 vía MQTT)
#  ┌─────────────────────────────────────────┬─────────────────────────────┐
#  │ Tópico                                  │ Descripción                 │
#  ├─────────────────────────────────────────┼─────────────────────────────┤
#  │ sleepbear/cmd/ventilador                │ "ON" / "OFF"                │
#  │ sleepbear/cmd/musica                    │ "ON" / "OFF"                │
#  │ sleepbear/cmd/volumen                   │ Número 0–30                 │
#  │ sleepbear/cmd/led                       │ "verde"/"rojo"/"azul"/etc.  │
#  │ sleepbear/cmd/pista                     │ Número de pista 1–255       │
#  └─────────────────────────────────────────┴─────────────────────────────┘
#
#  ESTRUCTURA FIREBASE (nodos sincronizados con la app web)
#  sleepbear/
#  ├── sensores/
#  │   ├── temp_bebe            ← float °C   (ESP32 → Firebase)
#  │   ├── temp_cuarto          ← float °C
#  │   ├── humedad              ← int %
#  │   ├── nivel_luz            ← float %
#  │   └── nivel_sonido         ← float %
#  ├── alertas/
#  │   ├── fiebre               ← bool
#  │   ├── cuarto_caliente      ← bool
#  │   ├── llanto               ← bool
#  │   └── modo_noche           ← bool
#  ├── actuadores/              (app web → Firebase → ESP32)
#  │   ├── ventilador/activar   ← bool
#  │   ├── musica/activar       ← bool
#  │   ├── musica/volumen       ← int 0-30
#  │   ├── musica/pista         ← int 1-255
#  │   └── led/color            ← string
#  └── camara/                  (escrito por ESP32-CAM)
#      └── rostro_detectado     ← bool

# ── Tópicos MQTT de publicación (sensores → app web) ─────────────────────────
TOP_TEMP_BEBE    = b"sleepbear/sensores/temp_bebe"
TOP_TEMP_CUARTO  = b"sleepbear/sensores/temp_cuarto"
TOP_HUMEDAD      = b"sleepbear/sensores/humedad"
TOP_NIVEL_LUZ    = b"sleepbear/sensores/nivel_luz"
TOP_NIVEL_SONIDO = b"sleepbear/sensores/nivel_sonido"
TOP_AL_FIEBRE    = b"sleepbear/alertas/fiebre"
TOP_AL_CALOR     = b"sleepbear/alertas/cuarto_caliente"
TOP_AL_LLANTO    = b"sleepbear/alertas/llanto"
TOP_AL_NOCHE     = b"sleepbear/alertas/modo_noche"

# ── Tópicos MQTT de suscripción (app web → actuadores) ───────────────────────
TOP_CMD_VENTILADOR = b"sleepbear/cmd/ventilador"
TOP_CMD_MUSICA     = b"sleepbear/cmd/musica"
TOP_CMD_VOLUMEN    = b"sleepbear/cmd/volumen"
TOP_CMD_LED        = b"sleepbear/cmd/led"
TOP_CMD_PISTA      = b"sleepbear/cmd/pista"


# =============================================================================
#  INICIALIZACIÓN DE LA HAL
# =============================================================================

sensores     = CajaDeSensores()
actuadores   = CajaDeActuadores()
cliente_mqtt = None


# =============================================================================
#  FUNCIONES DE RED
# =============================================================================

def conectar_wifi():
    """
    Parámetros: ninguno.
    Acción:     Conecta el ESP32 a la red WiFi configurada y muestra
                la IP asignada al terminar. WiFi es requerido por
                tanto MQTT como Firebase.
    Retorna:    None.
    """
    print("Conectando a WiFi", end="")
    interfaz = network.WLAN(network.STA_IF)
    interfaz.active(True)
    interfaz.connect(SSID_WIFI, CLAVE_WIFI)
    while not interfaz.isconnected():
        print(".", end="")
        time.sleep(0.2)
    print(" ¡Conectado! IP:", interfaz.ifconfig()[0])


# =============================================================================
#  FUNCIONES MQTT
# =============================================================================

def cerrar_mqtt():
    """
    Parámetros: ninguno.
    Acción:     Cierra la sesión MQTT activa de forma segura.
                Ignora errores si la conexión ya estaba caída.
    Retorna:    None.
    """
    global cliente_mqtt
    if cliente_mqtt is not None:
        try:
            cliente_mqtt.disconnect()
        except:
            pass
    cliente_mqtt = None


def conectar_mqtt():
    """
    Parámetros: ninguno.
    Acción:     Crea una nueva conexión MQTT, registra el callback
                enrutar_comando_mqtt y suscribe a todos los tópicos
                de comandos de actuadores.
    Retorna:    None.
    """
    global cliente_mqtt
    cerrar_mqtt()
    cliente_mqtt = MQTTClient(
        ID_CLIENTE, SERVIDOR_MQTT, PUERTO_MQTT,
        USUARIO_MQTT, CLAVE_MQTT, keepalive=60
    )
    cliente_mqtt.set_callback(enrutar_comando_mqtt)
    cliente_mqtt.connect()
    cliente_mqtt.subscribe(TOP_CMD_VENTILADOR)
    cliente_mqtt.subscribe(TOP_CMD_MUSICA)
    cliente_mqtt.subscribe(TOP_CMD_VOLUMEN)
    cliente_mqtt.subscribe(TOP_CMD_LED)
    cliente_mqtt.subscribe(TOP_CMD_PISTA)
    print("MQTT conectado y suscrito a canales de comandos.")


def enrutar_comando_mqtt(topico, mensaje):
    """
    Parámetros: topico  (bytes) — nombre del tópico MQTT recibido.
                mensaje (bytes) — contenido del mensaje.
    Acción:     Callback principal de MQTT. Interpreta el tópico
                y delega la acción al actuador correspondiente a
                través de la HAL (dispositivos.py).
                Adicionalmente refleja el nuevo estado en Firebase
                para mantener consistencia entre MQTT y la app web.
                NUNCA accede directamente al hardware.
    Retorna:    None.
    """
    print("MQTT ► Tópico: %s | Mensaje: %s" % (topico, mensaje))

    # ── Comando: ventilador DC ────────────────────────────────
    if topico == TOP_CMD_VENTILADOR:
        if mensaje == b"ON":
            actuadores.activar_ventilador()
            # Reflejar en Firebase para mantener consistencia con app web
            firebase.put("sleepbear/actuadores/ventilador/activar",
                         True, bg=False)
        elif mensaje == b"OFF":
            actuadores.desactivar_ventilador()
            firebase.put("sleepbear/actuadores/ventilador/activar",
                         False, bg=False)

    # ── Comando: música de cuna (DFPlayer Mini) ───────────────
    elif topico == TOP_CMD_MUSICA:
        if mensaje == b"ON":
            actuadores.reproducir_musica_cuna()
            firebase.put("sleepbear/actuadores/musica/activar",
                         True, bg=False)
        elif mensaje == b"OFF":
            actuadores.detener_musica()
            firebase.put("sleepbear/actuadores/musica/activar",
                         False, bg=False)

    # ── Comando: ajuste de volumen del DFPlayer ───────────────
    elif topico == TOP_CMD_VOLUMEN:
        try:
            nivel = int(mensaje)
            actuadores.ajustar_volumen(nivel)
            firebase.put("sleepbear/actuadores/musica/volumen",
                         nivel, bg=False)
        except ValueError:
            print("[ERROR] Volumen inválido:", mensaje)

    # ── Comando: color / modo del LED RGB ─────────────────────
    elif topico == TOP_CMD_LED:
        color = mensaje.decode()
        if color == "verde":
            actuadores.indicar_todo_bien()
        elif color == "amarillo":
            actuadores.indicar_atencion()
        elif color == "rojo":
            actuadores.indicar_alerta()
        elif color == "azul":
            # Azul suave: modo calma para llanto
            actuadores.calmar_llanto()
        elif color == "noche":
            actuadores.modo_nocturno()
        elif color == "apagar":
            actuadores._establecer_color_led(0, 0, 0)
        firebase.put("sleepbear/actuadores/led/color", color, bg=False)

    # ── Comando: seleccionar pista de audio específica ────────
    elif topico == TOP_CMD_PISTA:
        try:
            pista = int(mensaje)
            actuadores.reproducir_musica_cuna(pista)
            firebase.put("sleepbear/actuadores/musica/pista",
                         pista, bg=False)
        except ValueError:
            print("[ERROR] Pista inválida:", mensaje)

    else:
        print("[WARN] Tópico no reconocido:", topico)

    gc.collect()
    print("Memoria libre:", gc.mem_free())


def publicar_sensores_mqtt(estado):
    """
    Parámetros: estado (dict) — resultado de obtener_estado_completo().
    Acción:     Publica la lectura de cada sensor y cada bandera de
                alerta en su tópico MQTT para que la app web los
                reciba en tiempo real.
    Retorna:    None.
    """
    if estado["temperatura_bebe"] is not None:
        cliente_mqtt.publish(TOP_TEMP_BEBE,
                             str(estado["temperatura_bebe"]).encode())
    if estado["temperatura_cuarto"] is not None:
        cliente_mqtt.publish(TOP_TEMP_CUARTO,
                             str(estado["temperatura_cuarto"]).encode())
    if estado["humedad_cuarto"] is not None:
        cliente_mqtt.publish(TOP_HUMEDAD,
                             str(estado["humedad_cuarto"]).encode())

    cliente_mqtt.publish(TOP_NIVEL_LUZ,
                         str(estado["nivel_luz"]).encode())
    cliente_mqtt.publish(TOP_NIVEL_SONIDO,
                         str(estado["nivel_sonido"]).encode())

    # Alertas como cadena "SI" / "NO" (compatible con app web y MQTT Explorer)
    cliente_mqtt.publish(TOP_AL_FIEBRE,
                         b"SI" if estado["hay_fiebre"] else b"NO")
    cliente_mqtt.publish(TOP_AL_CALOR,
                         b"SI" if estado["cuarto_caliente"] else b"NO")
    cliente_mqtt.publish(TOP_AL_LLANTO,
                         b"SI" if estado["llanto_detectado"] else b"NO")
    cliente_mqtt.publish(TOP_AL_NOCHE,
                         b"SI" if estado["esta_oscuro"] else b"NO")

    print("MQTT ► Telemetría publicada.")


# =============================================================================
#  FUNCIONES FIREBASE
# =============================================================================

def enviar_sensores_firebase(estado):
    """
    Parámetros: estado (dict) — resultado de obtener_estado_completo().
    Acción:     Persiste el estado completo de sensores y alertas en
                Firebase Realtime Database. La app web lee estos nodos
                para mostrar el dashboard, historial y activar notif-
                icaciones push. bg=False garantiza escritura síncrona.
    Retorna:    None.
    """
    # ── Telemetría numérica de sensores ───────────────────────
    if estado["temperatura_bebe"] is not None:
        firebase.put("sleepbear/sensores/temp_bebe",
                     estado["temperatura_bebe"], bg=False)
    if estado["temperatura_cuarto"] is not None:
        firebase.put("sleepbear/sensores/temp_cuarto",
                     estado["temperatura_cuarto"], bg=False)
    if estado["humedad_cuarto"] is not None:
        firebase.put("sleepbear/sensores/humedad",
                     estado["humedad_cuarto"], bg=False)

    firebase.put("sleepbear/sensores/nivel_luz",
                 estado["nivel_luz"], bg=False)
    firebase.put("sleepbear/sensores/nivel_sonido",
                 estado["nivel_sonido"], bg=False)

    # ── Banderas de alerta (booleanos para la app web) ────────
    firebase.put("sleepbear/alertas/fiebre",
                 estado["hay_fiebre"], bg=False)
    firebase.put("sleepbear/alertas/cuarto_caliente",
                 estado["cuarto_caliente"], bg=False)
    firebase.put("sleepbear/alertas/llanto",
                 estado["llanto_detectado"], bg=False)
    firebase.put("sleepbear/alertas/modo_noche",
                 estado["esta_oscuro"], bg=False)

    gc.collect()
    print("Firebase ► Sensores sincronizados. Mem libre:", gc.mem_free())


def leer_comandos_firebase():
    """
    Parámetros: ninguno.
    Acción:     Consulta el nodo /sleepbear/actuadores/ en Firebase
                y ejecuta comandos pendientes enviados desde la app web.
                Este canal es el complemento al MQTT: funciona aunque
                la app web no tenga WebSocket activo.
                Los flags booleanos se resetean a False tras ejecutarse
                para evitar que el mismo comando se repita en el
                siguiente ciclo de sincronización.
    Retorna:    None.
    """
    # ── Ventilador: activar / desactivar ─────────────────────
    firebase.get("sleepbear/actuadores/ventilador/activar", "fb_ventilador")
    estado_vent = getattr(firebase, "fb_ventilador", None)
    if estado_vent is True:
        actuadores.activar_ventilador()
        firebase.put("sleepbear/actuadores/ventilador/activar",
                     False, bg=False)
        print("Firebase ► Ventilador activado desde app web.")
    elif estado_vent is False:
        actuadores.desactivar_ventilador()

    # ── Música: reproducir / detener ─────────────────────────
    firebase.get("sleepbear/actuadores/musica/activar", "fb_musica")
    if getattr(firebase, "fb_musica", None) is True:
        actuadores.reproducir_musica_cuna()
        firebase.put("sleepbear/actuadores/musica/activar",
                     False, bg=False)
        print("Firebase ► Música iniciada desde app web.")

    # ── Volumen ───────────────────────────────────────────────
    firebase.get("sleepbear/actuadores/musica/volumen", "fb_volumen")
    vol = getattr(firebase, "fb_volumen", None)
    if vol is not None:
        actuadores.ajustar_volumen(int(vol))

    # ── Color del LED RGB ─────────────────────────────────────
    firebase.get("sleepbear/actuadores/led/color", "fb_led")
    color = getattr(firebase, "fb_led", None)
    if color == "verde":
        actuadores.indicar_todo_bien()
    elif color == "amarillo":
        actuadores.indicar_atencion()
    elif color == "rojo":
        actuadores.indicar_alerta()
    elif color == "azul":
        actuadores.calmar_llanto()
    elif color == "noche":
        actuadores.modo_nocturno()

    # ── Pista de audio específica ─────────────────────────────
    firebase.get("sleepbear/actuadores/musica/pista", "fb_pista")
    pista = getattr(firebase, "fb_pista", None)
    if pista is not None:
        actuadores.reproducir_musica_cuna(int(pista))


# =============================================================================
#  BUCLE PRINCIPAL
# =============================================================================

def iniciar_sistema():
    """
    Parámetros: ninguno.
    Acción:     Bucle principal NO BLOQUEANTE con 3 tareas temporizadas:
                  Tarea 1 — check_msg() MQTT cada ~50 ms para recibir
                             comandos desde la app web en tiempo real.
                  Tarea 2 — publicar telemetría de sensores por MQTT
                             cada INTERVALO_MQTT ms.
                  Tarea 3 — sincronizar Firebase cada INTERVALO_FIREBASE
                             ms: persiste sensores y lee comandos web.
                Incluye reconexión automática de MQTT ante caídas.
    Retorna:    None (bucle infinito hasta KeyboardInterrupt).
    """
    ultimo_mqtt     = time.ticks_ms()
    ultimo_firebase = time.ticks_ms()

    actuadores.indicar_todo_bien()
    print("SleepBear — MQTT + Firebase iniciado y operando.")

    while True:
        ahora = time.ticks_ms()

        # ── TAREA 1: revisar mensajes MQTT ────────────────────
        try:
            cliente_mqtt.check_msg()
        except OSError as e:
            print("[MQTT] Conexión perdida (%s). Reconectando..." % e)
            actuadores.indicar_atencion()
            time.sleep(3)
            try:
                conectar_mqtt()
                actuadores.indicar_todo_bien()
                print("[MQTT] Reconexión exitosa.")
            except OSError:
                print("[MQTT] Reintento fallido, esperando 10s...")
                time.sleep(10)

        # ── TAREA 2: publicar sensores por MQTT ──────────────
        if time.ticks_diff(ahora, ultimo_mqtt) >= INTERVALO_MQTT:
            try:
                estado = sensores.obtener_estado_completo()
                publicar_sensores_mqtt(estado)
                ultimo_mqtt = ahora
            except OSError as e:
                print("[MQTT] Error al publicar:", e)

        # ── TAREA 3: sincronizar Firebase ────────────────────
        if time.ticks_diff(ahora, ultimo_firebase) >= INTERVALO_FIREBASE:
            try:
                estado = sensores.obtener_estado_completo()
                enviar_sensores_firebase(estado)    # ESP32  → Firebase
                leer_comandos_firebase()            # Firebase → ESP32
                ultimo_firebase = ahora
            except Exception as e:
                print("[Firebase] Error de sincronización:", e)

        time.sleep_ms(50)


# =============================================================================
#  PUNTO DE ENTRADA
# =============================================================================

try:
    conectar_wifi()
    firebase.setURL(FIREBASE_URL)    # Inicializar Firebase con URL del proyecto
    conectar_mqtt()
    iniciar_sistema()

except KeyboardInterrupt:
    print("\n[SISTEMA] Apagado solicitado.")
    actuadores.estado_seguro()
    cerrar_mqtt()
    print("[SISTEMA] SleepBear apagado correctamente.")
