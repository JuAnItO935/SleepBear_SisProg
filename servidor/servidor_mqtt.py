# ========================= servidor_mqtt.py =========================
"""
OBJETIVO: Servidor Python para SleepBear. Actúa como puente MQTT:
          recibe telemetría de TODOS los sensores del ESP32 con timestamp,
          imprime los datos en consola para validación, toma decisiones
          basadas en la lógica de prioridades del sistema y publica
          comandos de respuesta hacia los actuadores físicos.
          Demuestra el flujo obligatorio del curso:
          ESP32 → MQTT Broker → Python (procesamiento) → MQTT → Actuadores.
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
             Cortez Iñiguez Juan José - 21240173
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

import paho.mqtt.client as mqtt
import json
from datetime import datetime

# =========================================================
# CONFIGURACIÓN MQTT
# Broker público gratuito — no requiere autenticación.
# =========================================================
BROKER    = "broker.hivemq.com"
PORT      = 1883
CLIENT_ID = "sleepbear_servidor_01"

# =========================================================
# MATRIZ DE TÓPICOS MQTT
# Espejo exacto de los definidos en main_mqtt.py del ESP32.
# Formato: proyecto/tipo_nodo/modulo/id
# =========================================================

# Escuchar: servidor recibe telemetría del ESP32
T_ESTADO   = "sleepbear/sensor/estado/01"       # Estado completo del sistema
T_MLX      = "sleepbear/sensor/mlx90614/01"     # Temperatura del bebé
T_DHT      = "sleepbear/sensor/dht11/01"        # Temperatura y humedad del cuarto
T_LDR      = "sleepbear/sensor/ldr/01"          # Nivel de luz ambiental
T_MIC      = "sleepbear/sensor/microfono/01"    # Nivel de sonido / llanto

# Publicar: servidor envía comandos al ESP32
T_CMD_LED  = "sleepbear/comando/led/01"         # Control del LED RGB
T_CMD_FAN  = "sleepbear/comando/ventilador/01"  # Control del ventilador DC
T_CMD_AUD  = "sleepbear/comando/audio/01"       # Control del DFPlayer Mini
T_CMD_SIS  = "sleepbear/comando/sistema/01"     # Comandos globales del sistema

# =========================================================
# TIMESTAMP
# Genera marca de tiempo para cada evento registrado.
# Requerimiento explícito de la práctica.
# =========================================================
def ts():
    """Retorna timestamp legible en formato HH:MM:SS."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# =========================================================
# PUBLICAR COMANDOS
# Serializa el payload a JSON y lo publica con QoS 1
# para garantizar al menos una entrega al ESP32.
# =========================================================
def pub(client, topic, data):
    """Publica un comando JSON al ESP32 con QoS 1."""
    msg = json.dumps(data)
    client.publish(topic, msg, qos=1)
    print(f"  [→ COMANDO] {topic.split('/')[2].upper()}: {msg}")

# =========================================================
# LÓGICA DE DECISIÓN
# Evalúa el estado completo recibido y decide qué comandos
# enviar siguiendo la jerarquía de prioridades:
#   Prioridad 0: llanto detectado  → alerta máxima
#   Prioridad 1: fiebre del bebé   → alerta crítica
#   Prioridad 2: cuarto caliente   → atención
#   Prioridad 3: todo normal       → estado seguro
# El modo nocturno se evalúa siempre, independientemente.
# =========================================================
def tomar_decision(client, estado):
    """
    Analiza el estado del sistema y publica comandos de respuesta.
    Los comandos se envían al ESP32 que los ejecuta a través de la HAL.
    """
    llanto = estado.get("llanto_detectado", False)
    fiebre = estado.get("hay_fiebre",       False)
    calor  = estado.get("cuarto_caliente",  False)
    oscuro = estado.get("esta_oscuro",      False)

    if llanto:
        # Máxima urgencia — respuesta inmediata al llanto
        pub(client, T_CMD_LED, {"color": "rojo"})
        pub(client, T_CMD_AUD, {"accion": "reproducir", "pista": 1})

    elif fiebre:
        # Temperatura del bebé ≥ 38°C — alerta crítica
        pub(client, T_CMD_LED, {"color": "rojo"})
        pub(client, T_CMD_AUD, {"accion": "reproducir", "pista": 1})

    elif calor:
        # Temperatura del cuarto ≥ 28°C — activar ventilador
        pub(client, T_CMD_LED, {"color": "amarillo"})
        pub(client, T_CMD_FAN, {"activar": True})

    else:
        # Todo normal — apagar actuadores
        pub(client, T_CMD_LED, {"color": "verde"})
        pub(client, T_CMD_FAN, {"activar": False})
        pub(client, T_CMD_AUD, {"accion": "detener"})

    # Modo nocturno independiente de prioridades
    if oscuro:
        pub(client, T_CMD_SIS, {"modo": "nocturno"})

# =========================================================
# CALLBACK: on_connect
# Se ejecuta automáticamente cuando el cliente se conecta
# al broker MQTT. Aquí se suscriben los tópicos de telemetría
# usando comodín # para capturar todos los subtópicos.
# =========================================================
def on_connect(client, userdata, flags, rc):
    """
    Callback de conexión al broker.
    Suscribe a sleepbear/# para recibir toda la telemetría del ESP32.
    """
    if rc == 0:
        print(f"\n[{ts()}] ✅ CONECTADO A {BROKER}")
        # Suscripción con comodín — captura todos los tópicos sleepbear/
        client.subscribe("sleepbear/#")
        print(f"[{ts()}] SUSCRITO A sleepbear/#")
        print(f"[{ts()}] Esperando datos del ESP32...")
        print("=" * 55)
    else:
        print(f"[ERROR] Fallo de conexión — código: {rc}")

# =========================================================
# CALLBACK: on_message
# Se ejecuta por cada mensaje recibido en cualquier tópico
# suscrito. Enruta según el tópico:
#   T_ESTADO → imprimir telemetría completa + tomar decisión
#   Otros    → imprimir para diagnóstico individual
# =========================================================
def on_message(client, userdata, msg):
    """
    Callback principal de mensajes entrantes.
    Imprime timestamp + datos recibidos y toma decisión si
    el tópico es el estado completo del sistema.
    """
    topic   = msg.topic
    payload = msg.payload.decode()

    # Tópico de estado completo → procesar y tomar decisión
    if topic == T_ESTADO:
        try:
            estado = json.loads(payload)

            # Imprimir telemetría con timestamp — requerido por la práctica
            print(f"\n[{ts()}] TELEMETRÍA RECIBIDA")
            print(f"  Sensor MLX90614 : T. bebé   = {estado.get('temperatura_bebe')}°C")
            print(f"  Sensor DHT11    : T. cuarto = {estado.get('temperatura_cuarto')}°C")
            print(f"  Sensor DHT11    : Humedad   = {estado.get('humedad_cuarto')}%")
            print(f"  Sensor LDR      : Luz       = {estado.get('nivel_luz')}%")
            print(f"  Sensor KY-037   : Sonido    = {estado.get('nivel_sonido')}%")
            print(f"  Análisis HAL    : Llanto    = {estado.get('llanto_detectado')}")
            print(f"  Análisis HAL    : Fiebre    = {estado.get('hay_fiebre')}")

            # Tomar decisión y publicar comandos al ESP32
            tomar_decision(client, estado)
            print("=" * 55)

        except Exception as e:
            print(f"[{ts()}] [ERROR JSON] {e}")

    # Tópicos individuales → mostrar para diagnóstico
    elif topic in [T_MLX, T_DHT, T_LDR, T_MIC]:
        nombre = topic.split("/")[2].upper()
        print(f"[{ts()}] [{nombre}] {payload}")

# =========================================================
# CALLBACK: on_disconnect
# =========================================================
def on_disconnect(client, userdata, rc):
    """Callback de desconexión — informa el evento."""
    print(f"[{ts()}] DESCONECTADO (rc={rc})")

# =========================================================
# MAIN
# =========================================================
print(f"[{ts()}] INICIANDO SERVIDOR MQTT — SleepBear")
print(f"[{ts()}] Broker: {BROKER}:{PORT}")

# Usar CallbackAPIVersion.VERSION2 para evitar DeprecationWarning
# en versiones recientes de paho-mqtt (2.x)
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                     client_id=CLIENT_ID)

client.on_connect    = on_connect
client.on_message    = on_message
client.on_disconnect = on_disconnect

client.connect(BROKER, PORT, 60)

# loop_forever() mantiene el cliente escuchando indefinidamente.
# Presiona Ctrl+C para detenerlo.
client.loop_forever()