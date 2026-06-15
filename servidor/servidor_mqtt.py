# ========================= servidor_mqtt.py =========================
"""
OBJETIVO: Gestión de Firebase y Dashboard de usuario.
          Servidor Python para SleepBear. Actúa como puente MQTT:
          recibe telemetría de TODOS los sensores del ESP32 con timestamp,
          toma decisiones basadas en la lógica de prioridades del sistema
          y publica comandos SOLO cuando el estado cambia (evita loops).
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

import paho.mqtt.client as mqtt
import json
from datetime import datetime

BROKER    = "broker.hivemq.com"
PORT      = 1883
CLIENT_ID = "sleepbear_servidor_01"

T_ESTADO   = "sleepbear/sensor/estado/01"
T_MLX      = "sleepbear/sensor/mlx90614/01"
T_DHT      = "sleepbear/sensor/dht11/01"
T_LDR      = "sleepbear/sensor/ldr/01"
T_MIC      = "sleepbear/sensor/microfono/01"

T_CMD_LED  = "sleepbear/comando/led/01"
T_CMD_FAN  = "sleepbear/comando/ventilador/01"
T_CMD_AUD  = "sleepbear/comando/audio/01"
T_CMD_SIS  = "sleepbear/comando/sistema/01"

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# =========================================================
# FIX MÚSICA EN LOOP: guardar el estado anterior para solo
# publicar comandos cuando el estado CAMBIA, no en cada ciclo.
# Sin esto, el servidor manda "reproducir" cada 3 segundos
# y el DFPlayer reinicia la pista antes de terminarla.
# =========================================================
estado_anterior = {
    "llanto": None,
    "fiebre": None,
    "calor":  None,
    "oscuro": None,
}

def pub(client, topic, data):
    msg = json.dumps(data)
    client.publish(topic, msg, qos=1)
    print(f"  [→ COMANDO] {topic.split('/')[2].upper()}: {msg}")

def tomar_decision(client, estado):
    global estado_anterior

    llanto = estado.get("llanto_detectado", False)
    fiebre = estado.get("hay_fiebre",       False)
    calor  = estado.get("cuarto_caliente",  False)

    # FIX LDR AL REVÉS: esta_oscuro viene invertido del ESP32.
    # El LDR en el proyecto es activo alto (1=luz, 0=oscuro),
    # pero la HAL devuelve value()==0 como oscuro. Si en tu
    # circuito es al revés (1=oscuro), invertimos aquí sin
    # tocar el ESP32.
    oscuro = not estado.get("esta_oscuro", False)

    # Solo actuar si el estado cambió respecto al ciclo anterior
    cambio = (
        llanto != estado_anterior["llanto"] or
        fiebre != estado_anterior["fiebre"] or
        calor  != estado_anterior["calor"]  or
        oscuro != estado_anterior["oscuro"]
    )

    if not cambio:
        print("  [=] Sin cambio de estado — sin comandos nuevos")
        return

    # Actualizar estado anterior
    estado_anterior["llanto"] = llanto
    estado_anterior["fiebre"] = fiebre
    estado_anterior["calor"]  = calor
    estado_anterior["oscuro"] = oscuro

    # Prioridad 0: llanto
    if llanto:
        pub(client, T_CMD_LED, {"color": "azul"})
        pub(client, T_CMD_AUD, {"accion": "reproducir", "pista": 1})

    # Prioridad 1: fiebre
    elif fiebre:
        pub(client, T_CMD_LED, {"color": "rojo"})
        pub(client, T_CMD_AUD, {"accion": "reproducir", "pista": 1})

    # Prioridad 2: cuarto caliente
    elif calor:
        pub(client, T_CMD_LED, {"color": "amarillo"})
        pub(client, T_CMD_FAN, {"activar": True})

    # Prioridad 3: todo normal
    else:
        pub(client, T_CMD_LED, {"color": "verde"})
        pub(client, T_CMD_FAN, {"activar": False})
        # FIX MÚSICA EN LOOP: solo detener si venimos de un estado
        # donde la música estaba activa (llanto o fiebre previos)
        if estado_anterior["llanto"] or estado_anterior["fiebre"]:
            pub(client, T_CMD_AUD, {"accion": "detener"})

    # Modo nocturno — independiente de prioridades
    if oscuro:
        pub(client, T_CMD_SIS, {"modo": "nocturno"})

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"\n[{ts()}] ✅ CONECTADO A {BROKER}")
        client.subscribe("sleepbear/#")
        print(f"[{ts()}] SUSCRITO A sleepbear/#")
        print(f"[{ts()}] Esperando datos del ESP32...")
        print("=" * 55)
    else:
        print(f"[ERROR] Fallo de conexión — código: {rc}")

def on_message(client, userdata, msg):
    topic   = msg.topic
    payload = msg.payload.decode()

    if topic == T_ESTADO:
        try:
            estado = json.loads(payload)
            print(f"\n[{ts()}] TELEMETRÍA RECIBIDA")
            print(f"  Sensor MLX90614 : T. bebé   = {estado.get('temperatura_bebe')}°C")
            print(f"  Sensor DHT11    : T. cuarto = {estado.get('temperatura_cuarto')}°C")
            print(f"  Sensor DHT11    : Humedad   = {estado.get('humedad_cuarto')}%")
            print(f"  Sensor LDR      : Luz       = {estado.get('nivel_luz')}")
            print(f"  Sensor KY-037   : Sonido    = {estado.get('nivel_sonido')}%")
            print(f"  Análisis HAL    : Llanto    = {estado.get('llanto_detectado')}")
            print(f"  Análisis HAL    : Fiebre    = {estado.get('hay_fiebre')}")
            tomar_decision(client, estado)
            print("=" * 55)
        except Exception as e:
            print(f"[{ts()}] [ERROR JSON] {e}")

    elif topic in [T_MLX, T_DHT, T_LDR, T_MIC]:
        nombre = topic.split("/")[2].upper()
        print(f"[{ts()}] [{nombre}] {payload}")

def on_disconnect(client, userdata, disconnect_flags, rc, properties=None):
    print(f"[{ts()}] DESCONECTADO (rc={rc})")

print(f"[{ts()}] INICIANDO SERVIDOR MQTT — SleepBear")
print(f"[{ts()}] Broker: {BROKER}:{PORT}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
client.on_connect    = on_connect
client.on_message    = on_message
client.on_disconnect = on_disconnect
client.connect(BROKER, PORT, 60)
client.loop_forever()