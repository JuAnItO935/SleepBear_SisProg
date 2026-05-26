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
from umqtt.simple import MQTTClient

# Importación de la capa HAL — único punto de acceso al hardware.
# Ningún Pin(), ADC(), I2C(), PWM() o UART() se llama fuera de estas clases.
from dispositivos import CajaDeSensores, CajaDeActuadores

# =========================================================
# CONFIGURACIÓN WIFI
# La ESP32 solo soporta redes 2.4 GHz, no 5 GHz.
# =========================================================
WIFI_SSID     = "Megcable_2.4G_AA78"
WIFI_PASSWORD = "MCT6FQYb"

# =========================================================
# CONFIGURACIÓN MQTT
# Broker público gratuito — no requiere autenticación.
# =========================================================
BROKER    = "broker.hivemq.com"
CLIENT_ID = "sleepbear_esp32_01"

# =========================================================
# MATRIZ DE TÓPICOS MQTT
# Formato obligatorio: proyecto/tipo_nodo/modulo/id
#
# Nivel 1 — sleepbear    : nombre del proyecto
# Nivel 2 — sensor       : datos de salida del hardware
#            comando      : instrucciones hacia el hardware
#            actuador     : estado operativo del actuador
# Nivel 3 — nombre del módulo físico
# Nivel 4 — 01           : ID único del nodo
# =========================================================

# Publicación: ESP32 → Broker → Servidor (telemetría de sensores)
T_ESTADO   = b"sleepbear/sensor/estado/01"      # Estado completo del sistema
T_MLX      = b"sleepbear/sensor/mlx90614/01"    # Temperatura del bebé (infrarrojo)
T_DHT      = b"sleepbear/sensor/dht11/01"       # Temperatura y humedad del cuarto
T_LDR      = b"sleepbear/sensor/ldr/01"         # Nivel de luz ambiental
T_MIC      = b"sleepbear/sensor/microfono/01"   # Nivel de sonido / detección de llanto

# Suscripción: Servidor → Broker → ESP32 (comandos hacia actuadores)
T_CMD_LED  = b"sleepbear/comando/led/01"        # Control del LED RGB de estado
T_CMD_FAN  = b"sleepbear/comando/ventilador/01" # Control del ventilador DC
T_CMD_AUD  = b"sleepbear/comando/audio/01"      # Control del DFPlayer Mini
T_CMD_SIS  = b"sleepbear/comando/sistema/01"    # Comandos globales del sistema

# =========================================================
# INSTANCIAS HAL
# CajaDeSensores y CajaDeActuadores son la única interfaz
# permitida para interactuar con el hardware físico.
# Encapsulan I2C, ADC, PWM y UART internamente.
# =========================================================
sensores   = CajaDeSensores()
actuadores = CajaDeActuadores()

# =========================================================
# CONEXIÓN WIFI
# =========================================================
def conectar_wifi():
    """Conecta al WiFi y bloquea hasta lograr conexión."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("[WIFI] Conectando a:", WIFI_SSID)
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        while not wlan.isconnected():
            print(".", end="")
            time.sleep(1)
    print("\n[WIFI] CONECTADO")
    print("IP:", wlan.ifconfig()[0])

# =========================================================
# CALLBACK: on_comando
# Se ejecuta automáticamente cada vez que llega un mensaje
# en cualquiera de los tópicos de comando suscritos.
#
# INTEGRACIÓN CON HAL:
# Este callback NUNCA accede directamente al hardware.
# Cada comando recibido se traduce en una llamada a la HAL:
#   LED     → actuadores.indicar_alerta() / indicar_atencion() / etc.
#   FAN     → actuadores.activar_ventilador() / desactivar_ventilador()
#   AUDIO   → actuadores.reproducir_musica_cuna() / detener_musica()
#   SISTEMA → actuadores.modo_nocturno() / estado_seguro()
# =========================================================
def on_comando(topic, payload):
    """
    Callback MQTT para comandos entrantes desde el servidor.
    Delega SIEMPRE a la HAL — sin acceso directo a hardware.
    """
    try:
        t   = topic.decode()
        cmd = ujson.loads(payload.decode())
        print("\n[COMANDO RECIBIDO]")
        print("TOPIC:", t)
        print("CMD:", cmd)

        # ── Control del LED RGB ───────────────────────────
        # La HAL gestiona los valores PWM de cada canal internamente.
        if t == "sleepbear/comando/led/01":
            color = cmd.get("color", "")
            if color == "rojo":
                actuadores.indicar_alerta()       # HAL: PWM R=1023, G=0, B=0
            elif color == "amarillo":
                actuadores.indicar_atencion()     # HAL: PWM R=800, G=400, B=0
            elif color == "verde":
                actuadores.indicar_todo_bien()    # HAL: PWM R=0, G=800, B=0
            elif color == "azul":
                actuadores.calmar_llanto()        # HAL: PWM R=0, G=0, B=800

        # ── Control del ventilador DC ─────────────────────
        # La HAL gestiona el transistor NPN (GPIO 32) internamente.
        elif t == "sleepbear/comando/ventilador/01":
            if cmd.get("activar"):
                actuadores.activar_ventilador()   # HAL: GPIO 32 HIGH
            else:
                actuadores.desactivar_ventilador()# HAL: GPIO 32 LOW

        # ── Control del DFPlayer Mini (audio) ─────────────
        # La HAL gestiona el protocolo UART de 10 bytes internamente.
        elif t == "sleepbear/comando/audio/01":
            accion = cmd.get("accion", "")
            if accion == "reproducir":
                actuadores.reproducir_musica_cuna(cmd.get("pista", 1))
            elif accion == "detener":
                actuadores.detener_musica()
            elif accion == "volumen":
                actuadores.ajustar_volumen(cmd.get("nivel", 15))

        # ── Comandos globales del sistema ──────────────────
        elif t == "sleepbear/comando/sistema/01":
            modo = cmd.get("modo", "")
            if modo == "nocturno":
                actuadores.modo_nocturno()        # HAL: volumen 8, LED mínimo
            elif modo == "seguro":
                actuadores.estado_seguro()        # HAL: apaga todo

    except Exception as e:
        print("[ERROR MQTT]", e)

# =========================================================
# PUBLICAR TELEMETRÍA
# Publica el estado de cada sensor en su tópico individual
# y también el estado completo en T_ESTADO.
# Los datos provienen EXCLUSIVAMENTE de la HAL mediante
# sensores.obtener_estado_completo().
# =========================================================
def publicar_telemetria(cli, estado):
    """Publica telemetría completa e individual de todos los sensores."""

    # Estado completo — usado por el servidor para tomar decisiones
    cli.publish(T_ESTADO, ujson.dumps(estado))

    # MLX90614 — temperatura corporal del bebé sin contacto (I2C)
    cli.publish(T_MLX, ujson.dumps({
        "temp_bebe":  estado["temperatura_bebe"],
        "hay_fiebre": estado["hay_fiebre"]
    }))

    # DHT11 — temperatura y humedad del cuarto (1-Wire)
    cli.publish(T_DHT, ujson.dumps({
        "temp_cuarto": estado["temperatura_cuarto"],
        "humedad":     estado["humedad_cuarto"]
    }))

    # LDR — nivel de luz ambiental (ADC)
    cli.publish(T_LDR, ujson.dumps({
        "nivel_luz":  estado["nivel_luz"],
        "esta_oscuro": estado["esta_oscuro"]
    }))

    # KY-037 — nivel de sonido y detección de llanto (ADC + Digital)
    cli.publish(T_MIC, ujson.dumps({
        "nivel_sonido":     estado["nivel_sonido"],
        "llanto_detectado": estado["llanto_detectado"]
    }))

# =========================================================
# MAIN
# =========================================================
def main():
    # 1. Conectar a la red WiFi
    conectar_wifi()

    # 2. Configurar cliente MQTT y registrar el callback de comandos
    cli = MQTTClient(CLIENT_ID, BROKER, port=1883, keepalive=60)
    cli.set_callback(on_comando)
    cli.connect()
    print("\n[MQTT] CONECTADO A", BROKER)

    # 3. Suscribirse a los 4 tópicos de comando (QoS 0 por defecto en umqtt)
    cli.subscribe(T_CMD_LED)   # Comandos para el LED RGB
    cli.subscribe(T_CMD_FAN)   # Comandos para el ventilador
    cli.subscribe(T_CMD_AUD)   # Comandos para el audio
    cli.subscribe(T_CMD_SIS)   # Comandos de sistema
    print("[MQTT] SUSCRIPCIONES OK")

    while True:
        # check_msg() es NO bloqueante — verifica si llegó algún comando
        # sin detener el bucle. Si se usara wait_msg() el programa
        # se detendría esperando y no leería sensores.
        cli.check_msg()

        # Una sola llamada a la HAL obtiene el estado completo.
        # obtener_estado_completo() incluye detectar_llanto() que
        # toma 5 muestras × 40ms para evitar falsas alarmas.
        estado = sensores.obtener_estado_completo()

        # Publicar toda la telemetría en MQTT
        publicar_telemetria(cli, estado)

        print("\n[SENSORES]")
        print(estado)

        # Revisar comandos adicionales durante la espera
        for _ in range(20):
            cli.check_msg()
            time.sleep_ms(100)

main()