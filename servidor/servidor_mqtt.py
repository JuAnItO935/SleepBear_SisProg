"""
OBJETIVO: Servidor Python para SleepBear. Actúa como puente MQTT:
          recibe telemetría de todos los sensores del ESP32 con timestamp,
          procesa la información y publica comandos de respuesta para
          controlar los actuadores. Demuestra el flujo obligatorio:
          ESP32 → MQTT Broker → Python (procesamiento) → MQTT → Actuadores.
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

import paho.mqtt.client as mqtt
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
# Las credenciales NUNCA van hardcodeadas en el código
load_dotenv()

BROKER    = os.getenv("MQTT_BROKER", "broker.hivemq.com")
PORT      = int(os.getenv("MQTT_PORT", "1883"))
CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "sleepbear_servidor_01")

# ═══════════════════════════════════════════════════════════
# TÓPICOS — Espejo exacto de main_mqtt.py
# ═══════════════════════════════════════════════════════════
T_ESTADO   = "sleepbear/sensor/estado/01"
T_MLX      = "sleepbear/sensor/mlx90614/01"
T_DHT      = "sleepbear/sensor/dht11/01"
T_LDR      = "sleepbear/sensor/ldr/01"
T_MIC      = "sleepbear/sensor/microfono/01"
T_CMD_LED  = "sleepbear/comando/led/01"
T_CMD_FAN  = "sleepbear/comando/ventilador/01"
T_CMD_AUD  = "sleepbear/comando/audio/01"
T_CMD_SIS  = "sleepbear/comando/sistema/01"

# ═══════════════════════════════════════════════════════════
# UTILIDADES
# ═══════════════════════════════════════════════════════════
def ts():
    """Genera timestamp legible para los logs — requerido por la maestra."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def pub(client, topico, datos):
    """Publica un comando JSON con QoS 1 y lo imprime en consola."""
    msg = json.dumps(datos)
    client.publish(topico, msg, qos=1)
    modulo = topico.split("/")[2].upper()
    print(f"  [→ COMANDO] {modulo}: {msg}")

# ═══════════════════════════════════════════════════════════
# LÓGICA DE DECISIÓN
# Recibe el estado completo y decide qué comandos enviar.
# Sigue la jerarquía de prioridades: llanto > fiebre > calor.
# ═══════════════════════════════════════════════════════════
def tomar_decision(client, e):
    llanto = e.get("llanto_detectado", False)
    fiebre = e.get("hay_fiebre", False)
    calor  = e.get("cuarto_caliente", False)
    oscuro = e.get("esta_oscuro", False)

    if llanto:
        pub(client, T_CMD_LED, {"color": "rojo"})
        pub(client, T_CMD_AUD, {"accion": "reproducir", "pista": 1})
    elif fiebre:
        pub(client, T_CMD_LED, {"color": "rojo"})
        pub(client, T_CMD_AUD, {"accion": "reproducir", "pista": 1})
        pub(client, T_CMD_AUD, {"accion": "volumen", "nivel": 10})
    elif calor:
        pub(client, T_CMD_LED, {"color": "amarillo"})
        pub(client, T_CMD_FAN, {"activar": True})
    else:
        pub(client, T_CMD_LED, {"color": "verde"})
        pub(client, T_CMD_FAN, {"activar": False})
        pub(client, T_CMD_AUD, {"accion": "detener"})

    if oscuro:
        pub(client, T_CMD_SIS, {"modo": "nocturno"})

# ═══════════════════════════════════════════════════════════
# CALLBACK on_connect
# Se ejecuta cuando el servidor se conecta al broker.
# Aquí se suscriben TODOS los tópicos de telemetría.
# ═══════════════════════════════════════════════════════════
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[{ts()}] ✅ Conectado al broker: {BROKER}")
        # Suscribir al estado completo y a los tópicos individuales
        for t in [T_ESTADO, T_MLX, T_DHT, T_LDR, T_MIC]:
            client.subscribe(t)
        print(f"[{ts()}] Suscrito a 5 tópicos de telemetría.")
        print(f"[{ts()}] Esperando datos del ESP32...")
        print("=" * 60)
    else:
        print(f"[ERROR] Fallo al conectar — código: {rc}")

# ═══════════════════════════════════════════════════════════
# CALLBACK on_message
# Se ejecuta por CADA mensaje recibido.
# Enruta según el tópico y muestra el dato con timestamp.
# ═══════════════════════════════════════════════════════════
def on_message(client, userdata, msg):
    topico  = msg.topic
    payload = msg.payload.decode()

    # Tópico de estado completo → procesar y tomar decisión
    if topico == T_ESTADO:
        try:
            estado = json.loads(payload)
            # Imprimir telemetría con timestamp — requerido por la maestra
            print(f"[{ts()}] TELEMETRÍA RECIBIDA")
            print(f"  Sensor MLX90614: T. bebé   = {estado.get("temperatura_bebe")}°C")
            print(f"  Sensor DHT11:    T. cuarto = {estado.get("temperatura_cuarto")}°C")
            print(f"  Sensor DHT11:    Humedad   = {estado.get("humedad_cuarto")}%")
            print(f"  Sensor LDR:      Luz       = {estado.get("nivel_luz")}%")
            print(f"  Sensor KY-038:   Sonido    = {estado.get("nivel_sonido")}%")
            print(f"  Análisis HAL:    Llanto    = {estado.get("llanto_detectado")}")
            print(f"  Análisis HAL:    Fiebre    = {estado.get("hay_fiebre")}")
            # Tomar decisión y publicar comandos al ESP32
            tomar_decision(client, estado)
            print("=" * 60)
        except json.JSONDecodeError as e:
            print(f"[{ts()}] [ERROR] JSON inválido: {e}")

    # Tópicos individuales → solo mostrar para diagnóstico
    elif topico in [T_MLX, T_DHT, T_LDR, T_MIC]:
        nombre = topico.split("/")[2]
        print(f"[{ts()}] [{nombre.upper()}] {payload}")

def on_disconnect(client, userdata, rc):
    print(f"[{ts()}] Desconectado (rc={rc}). Reintentando...")

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
def main():
    print(f"[{ts()}] SleepBear — Servidor MQTT")
    print(f"[{ts()}] Broker: {BROKER}:{PORT}")

    client = mqtt.Client(client_id=CLIENT_ID)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    client.connect(BROKER, PORT, keepalive=60)
    # loop_forever() mantiene el cliente escuchando.
    # Presiona Ctrl+C para detenerlo limpiamente.
    client.loop_forever()

if __name__ == "__main__":
    main()
