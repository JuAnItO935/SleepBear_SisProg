# ========================= main_mqtt.py =========================
"""
OBJETIVO: Script principal de SleepBear con integración MQTT completa.
          Conecta la ESP32 a un broker MQTT, publica la telemetría de
          TODOS los sensores (MLX90614, DHT11, LDR, KY-037) en sus
          tópicos correspondientes y se suscribe a los comandos de
          TODOS los actuadores (LED RGB, ventilador DC, DFPlayer Mini).
          Toda interacción con hardware se delega EXCLUSIVAMENTE a la
          capa HAL (dispositivos.py), sin acceso directo a periféricos.
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
             Cortez Iñiguez Juan José - 21240173
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

import time
import ujson
import network
import gc
from umqtt.simple import MQTTClient
import ufirebase as firebase
import machine, ubinascii

from dispositivos import CajaDeSensores, CajaDeActuadores

# ── WiFi ──────────────────────────────────────────────────────────────────────
WIFI_SSID     = "Megcable_2.4G_AA78"    # <-- cambia a tu red
WIFI_PASSWORD = "MCT6FQYb"

# ── MQTT ──────────────────────────────────────────────────────────────────────
BROKER    = "broker.hivemq.com"
PORT      = 1883
CLIENT_ID = "sleepbear_esp32_" + ubinascii.hexlify(machine.unique_id()).decode()

# ── Firebase ──────────────────────────────────────────────────────────────────
FIREBASE_URL = "https://sleepbear-95f3e-default-rtdb.firebaseio.com/"

# ── Tópicos MQTT ──────────────────────────────────────────────────────────────
T_ESTADO   = b"sleepbear/sensor/estado/01"
T_CMD_LED  = b"sleepbear/comando/led/01"
T_CMD_FAN  = b"sleepbear/comando/ventilador/01"
T_CMD_AUD  = b"sleepbear/comando/audio/01"
T_CMD_SIS  = b"sleepbear/comando/sistema/01"

# ── Intervalos ────────────────────────────────────────────────────────────────
INTERVALO_MQTT     = 5000    # ms
INTERVALO_FIREBASE = 15000   # ms

# ── HAL ───────────────────────────────────────────────────────────────────────
sensores   = CajaDeSensores()
actuadores = CajaDeActuadores()
cliente    = None


# =============================================================================
# CONEXIÓN WIFI
# =============================================================================
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("[WIFI] Conectando a:", WIFI_SSID)
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        intentos = 0
        while not wlan.isconnected() and intentos < 30:
            print(".", end="")
            time.sleep(1)
            intentos += 1
    if wlan.isconnected():
        print("\n[WIFI] CONECTADO — IP:", wlan.ifconfig()[0])
        return True
    print("\n[WIFI] FALLO DE CONEXIÓN")
    return False


# =============================================================================
# CALLBACK MQTT — comandos entrantes
# =============================================================================
def on_comando(topic, payload):
    try:
        t   = topic.decode()
        cmd = ujson.loads(payload.decode())
        print("[CMD]", t, "→", cmd)

        if t == "sleepbear/comando/led/01":
            color = cmd.get("color", "")
            if   color == "rojo":     actuadores.indicar_alerta()
            elif color == "amarillo": actuadores.indicar_atencion()
            elif color == "verde":    actuadores.indicar_todo_bien()
            elif color == "azul":     actuadores.calmar_llanto()
            elif color == "noche":    actuadores.modo_nocturno()
            elif color == "apagar":   actuadores._establecer_color_led(0, 0, 0)

        elif t == "sleepbear/comando/ventilador/01":
            if cmd.get("activar"):
                actuadores.activar_ventilador()
            else:
                actuadores.desactivar_ventilador()

        elif t == "sleepbear/comando/audio/01":
            accion = cmd.get("accion", "")
            if accion == "reproducir":
                if not actuadores._musica_activa:
                    actuadores.reproducir_musica_cuna(cmd.get("pista", 1))
            elif accion == "detener":
                actuadores.detener_musica()
            elif accion == "volumen":
                actuadores.ajustar_volumen(cmd.get("nivel", 15))

        elif t == "sleepbear/comando/sistema/01":
            modo = cmd.get("modo", "")
            if   modo == "nocturno": actuadores.modo_nocturno()
            elif modo == "seguro":   actuadores.estado_seguro()

    except Exception as e:
        print("[ERROR CMD]", e)


# =============================================================================
# PUBLICAR TELEMETRÍA MQTT
# =============================================================================
def publicar_mqtt(estado):
    global cliente
    try:
        cliente.publish(T_ESTADO, ujson.dumps(estado))
        print("[MQTT] Telemetría publicada")
    except Exception as e:
        print("[MQTT] Error al publicar:", e)
        raise


# =============================================================================
# SINCRONIZAR FIREBASE
# FIX: Un único patch() en lugar de múltiples put().
# Esto soluciona que Firebase solo mostrara el último actuador (LED RGB):
# antes se hacían 12 llamadas put() individuales y el ESP32 agotaba los
# sockets antes de llegar a los sensores; solo el LED (última llamada que
# alcanzaba a completarse) aparecía en Firebase.
# Ahora todo sube en una sola transacción HTTPS.
# =============================================================================
def sincronizar_firebase(estado):
    try:
        # Nodo principal: telemetria/ultima — lo que lee el dashboard
        telemetria = {
            "temperatura_bebe":   estado["temperatura_bebe"],
            "temperatura_cuarto": estado["temperatura_cuarto"],
            "humedad_cuarto":     estado["humedad_cuarto"],
            "nivel_luz":          estado["nivel_luz"],
            "nivel_sonido":       estado["nivel_sonido"],
            "hay_fiebre":         estado["hay_fiebre"],
            "cuarto_caliente":    estado["cuarto_caliente"],
            "esta_oscuro":        estado["esta_oscuro"],
            "llanto_detectado":   estado["llanto_detectado"],
            "baseline_sonido":    estado["baseline_sonido"],
        }
        # FIX: patch() sube TODO de una vez — un solo socket HTTPS
        firebase.patch("telemetria/ultima", telemetria, bg=False)

        # Alertas individuales para el historial del dashboard
        firebase.patch("sleepbear/alertas", {
            "fiebre":        estado["hay_fiebre"],
            "cuarto_caliente": estado["cuarto_caliente"],
            "llanto":        estado["llanto_detectado"],
            "modo_noche":    estado["esta_oscuro"],
        }, bg=False)

        # FIX HEARTBEAT: el dashboard detecta si el ESP32 sigue vivo
        # comparando cuándo llegó la última actualización de este nodo.
        firebase.put("sistema/heartbeat", True, bg=False)
        firebase.put("sistema/online",    True, bg=False)

        print("[Firebase] Sync OK — mem:", gc.mem_free())
        gc.collect()

    except Exception as e:
        print("[Firebase] Error:", e)


# =============================================================================
# LEER COMANDOS DESDE FIREBASE (canal alternativo cuando no hay MQTT)
# =============================================================================
def leer_comandos_firebase():
    try:
        firebase.get("actuadores/comando_remoto", "fb_cmd")
        cmd = globals().get("fb_cmd", None)
        if not cmd or not isinstance(cmd, dict):
            return

        print("[Firebase→CMD]", cmd)

        if "color" in cmd:
            color = cmd["color"]
            if   color == "verde":    actuadores.indicar_todo_bien()
            elif color == "rojo":     actuadores.indicar_alerta()
            elif color == "amarillo": actuadores.indicar_atencion()
            elif color == "azul":     actuadores.calmar_llanto()
            elif color == "noche":    actuadores.modo_nocturno()
        elif "activar" in cmd:
            if cmd["activar"]: actuadores.activar_ventilador()
            else:              actuadores.desactivar_ventilador()
        elif "accion" in cmd:
            accion = cmd["accion"]
            if accion == "reproducir":
                if not actuadores._musica_activa:
                    actuadores.reproducir_musica_cuna(cmd.get("pista", 1))
            elif accion == "detener":
                actuadores.detener_musica()

        # Limpiar el nodo para no re-ejecutar el mismo comando
        firebase.put("actuadores/comando_remoto", None, bg=False)

    except Exception as e:
        print("[Firebase CMD] Error:", e)


# =============================================================================
# CONEXIÓN MQTT
# =============================================================================
def conectar_mqtt():
    global cliente
    if cliente is not None:
        try: cliente.disconnect()
        except: pass

    cliente = MQTTClient(CLIENT_ID, BROKER, PORT, keepalive=60)
    cliente.set_callback(on_comando)
    cliente.connect()
    cliente.subscribe(T_CMD_LED)
    cliente.subscribe(T_CMD_FAN)
    cliente.subscribe(T_CMD_AUD)
    cliente.subscribe(T_CMD_SIS)
    print("[MQTT] Conectado y suscrito")


# =============================================================================
# BUCLE PRINCIPAL
# =============================================================================
def iniciar():
    ultimo_mqtt     = time.ticks_ms()
    ultimo_firebase = time.ticks_ms()

    actuadores.indicar_todo_bien()
    print("[SleepBear] Sistema iniciado")

    while True:
        ahora = time.ticks_ms()

        # ── Revisar comandos MQTT ──────────────────────────────
        try:
            cliente.check_msg()
        except Exception as e:
            print("[MQTT] Reconectando:", e)
            actuadores.indicar_atencion()
            time.sleep(3)
            try:
                conectar_mqtt()
                actuadores.indicar_todo_bien()
            except:
                time.sleep(10)

        # ── Publicar sensores por MQTT ─────────────────────────
        if time.ticks_diff(ahora, ultimo_mqtt) >= INTERVALO_MQTT:
            estado = sensores.obtener_estado_completo()
            publicar_mqtt(estado)
            ultimo_mqtt = ahora

    # Decisiones locales sin depender del servidor de IA
    if estado["llanto_detectado"]:
        print("[DECISIÓN] LLANTO — música de cuna")
        actuadores.calmar_llanto()
    else:
        if actuadores._musica_activa:
            actuadores.detener_musica()
        actuadores.indicar_todo_bien()

    if estado["hay_fiebre"]:
        actuadores.activar_alerta_fiebre()

    if estado["cuarto_caliente"]:
        actuadores.activar_ventilador()
    else:
        actuadores.desactivar_ventilador()

        # ── Sincronizar Firebase ───────────────────────────────
        if time.ticks_diff(ahora, ultimo_firebase) >= INTERVALO_FIREBASE:
            estado = sensores.obtener_estado_completo()
            sincronizar_firebase(estado)
            leer_comandos_firebase()
            ultimo_firebase = ahora

        time.sleep_ms(50)


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================
try:
    if conectar_wifi():
        firebase.setURL(FIREBASE_URL)
        conectar_mqtt()
        iniciar()
    else:
        print("[ERROR] Sin WiFi — no se puede iniciar")

except KeyboardInterrupt:
    print("\n[SISTEMA] Apagando...")
    actuadores.estado_seguro()
    if cliente:
        try: cliente.disconnect()
        except: pass
    try: firebase.put("sistema/online", False, bg=False)
    except: pass
    print("[SISTEMA] Apagado correcto")


