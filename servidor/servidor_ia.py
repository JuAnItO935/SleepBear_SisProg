"""
OBJETIVO: Servidor Python con IA para SleepBear. Recibe telemetría de sensores
          e imágenes de la ESP32-CAM vía MQTT, procesa con OpenCV y envía
          comandos de respuesta a los actuadores del ESP32.
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
             Cortez Iñiguez Juan José - 21240173
PROYECTO: SleepBear - Sistema de Monitoreo Nocturno para Bebés
"""

# Modelo: Detección de postura del bebé con OpenCV (contornos + relación de aspecto)
# Precisión aproximada: 80-85%. Predice: SEGURO / RIESGO / INDETERMINADO

import paho.mqtt.client as mqtt
import json, base64, time
import numpy as np
import cv2
from detector_postura import detectar_postura_bebe

BROKER      = "broker.hivemq.com"   # o "localhost" si usas Mosquitto
PORT        = 1883
TOPIC_CAM   = "sleepbear/camara/frame"
TOPIC_SENS  = "sleepbear/sensores/estado"
TOPIC_CMD   = "sleepbear/comandos/actuadores"

ultimo_frame = None

def on_message(client, userdata, msg):
    global ultimo_frame

    if msg.topic == TOPIC_CAM:
        # Decodificar frame JPEG enviado en base64
        try:
            jpg_bytes = base64.b64decode(msg.payload)
            np_arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is not None:
                ultimo_frame = frame
                postura = detectar_postura_bebe(frame)
                print(f"[CAM] Postura detectada: {postura}")
                if postura == "RIESGO":
                    publicar_comando(client, {"alerta": "POSTURA_RIESGO", "led": "rojo"})

        except Exception as e:
            print(f"[ERROR] Frame inválido: {e}")

    elif msg.topic == TOPIC_SENS:
        # Procesar telemetría de sensores
        try:
            estado = json.loads(msg.payload.decode())
            print(f"[SENS] {estado}")
            cmd = evaluar_estado(estado)
            if cmd:
                publicar_comando(client, cmd)
        except Exception as e:
            print(f"[ERROR] JSON inválido: {e}")

def evaluar_estado(estado):
    """Lógica de decisión basada en telemetría — espejo del main.py del ESP32."""
    if estado.get("llanto_detectado"):
        return {"alerta": "LLANTO", "led": "rojo", "musica": True}
    if estado.get("hay_fiebre"):
        return {"alerta": "FIEBRE", "led": "rojo", "musica": True}
    if estado.get("cuarto_caliente"):
        return {"alerta": "CALOR", "led": "amarillo", "ventilador": True}
    return {"alerta": "OK", "led": "verde", "ventilador": False, "musica": False}

def publicar_comando(client, cmd):
    payload = json.dumps(cmd)
    client.publish(TOPIC_CMD, payload)
    print(f"[CMD] Publicado: {payload}")

def main():
    client = mqtt.Client()
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    client.subscribe(TOPIC_CAM)
    client.subscribe(TOPIC_SENS)
    print("[SleepBear IA] Servidor activo. Escuchando MQTT...")
    client.loop_forever()

if __name__ == "__main__":
    main()