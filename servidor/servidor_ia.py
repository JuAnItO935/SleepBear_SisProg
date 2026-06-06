"""
OBJETIVO: Servidor Python con IA para SleepBear. Recibe frames de la
          ESP32-CAM vía MQTT, aplica detección de postura del bebé con
          OpenCV y publica comandos de alerta si detecta posición de
          riesgo (boca abajo = riesgo SMSL). Demuestra el pipeline:
          ESP32-CAM → MQTT → Python+OpenCV → MQTT → Actuadores.
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

# Modelo: Detección de postura con OpenCV (Haar Cascades - Rostros)
# Precisión aproximada: 90-95% en iluminación normal
# Predicción: SEGURO / RIESGO / INDETERMINADO

import paho.mqtt.client as mqtt
import json
import base64
import numpy as np
import cv2
from datetime import datetime
from detector_postura import detectar_postura

# ══════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════
BROKER    = "broker.hivemq.com"
PORT      = 1883
CLIENT_ID = "sleepbear_ia_01"

# Tópicos
T_CAMARA     = "sleepbear/camara/frame/01"    # recibe frames de la cámara
T_CMD_LED    = "sleepbear/comando/led/01"     # envía comandos al LED
T_CMD_AUD    = "sleepbear/comando/audio/01"   # envía comandos al audio
T_CMD_SIS    = "sleepbear/comando/sistema/01" # comandos del sistema

# ══════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════
def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def pub(client, topic, data):
    client.publish(topic, json.dumps(data), qos=1)
    print(f"  [→ CMD] {topic.split('/')[2].upper()}: {json.dumps(data)}")

# ══════════════════════════════════════════
# CALLBACK on_connect
# Suscribirse al tópico de frames de la cámara
# ══════════════════════════════════════════
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[{ts()}] ✅ Conectado al broker")
        client.subscribe(T_CAMARA)
        print(f"[{ts()}] Suscrito a {T_CAMARA}")
        print(f"[{ts()}] Esperando frames de la ESP32-CAM...")
        print("=" * 55)

# ══════════════════════════════════════════
# CALLBACK on_message
# Recibe el frame, lo decodifica y corre la IA
# ══════════════════════════════════════════
def on_message(client, userdata, msg):
    if msg.topic != T_CAMARA:
        return

    try:
        # 1. Decodificar base64 → bytes JPEG
        jpg_bytes = base64.b64decode(msg.payload)

        # 2. Convertir bytes → array NumPy → imagen OpenCV
        np_arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
        frame  = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            print(f"[{ts()}] [WARN] Frame inválido, ignorando")
            return

        print(f"[DEBUG] Payload size: {len(msg.payload)} bytes")
        print(f"[DEBUG] Frame: {frame.shape if frame is not None else 'NONE'}")
        
        # 3. Correr el modelo de IA (Detector de Rostros corregido)
        postura = detectar_postura(frame)
        print(f"[{ts()}] [IA] Postura detectada: {postura}")

        # 4. Tomar decisión según el resultado
        if postura == "RIESGO":
            # Bebé boca abajo o cara tapada — alerta máxima
            print(f"[{ts()}] ⚠️  RIESGO DETECTADO — activando alerta")
            pub(client, T_CMD_LED, {"color": "rojo"})
            pub(client, T_CMD_AUD, {"accion": "reproducir", "pista": 1})

        elif postura == "SEGURO":
            # Bebé en posición normal — todo bien
            pub(client, T_CMD_LED, {"color": "verde"})

        # INDETERMINADO → no enviar comando, esperar siguiente frame

    except Exception as e:
        print(f"[{ts()}] [ERROR] {e}")


# ══════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════
def main():
    print(f"[{ts()}] SleepBear — Servidor IA")
    print(f"[{ts()}] Modelo: OpenCV — detección de postura del bebé")
    print(f"[{ts()}] Precisión aproximada: 90-95%")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()

if __name__ == "__main__":
    main()