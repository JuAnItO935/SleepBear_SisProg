"""
OBJETIVO: Captura frames con una webcam USB/integrada y los publica
          en MQTT para análisis de postura por el servidor de IA.
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

import cv2
import base64
import time
import paho.mqtt.client as mqtt

# ══════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════
BROKER    = "broker.hivemq.com"
PORT      = 1883
CLIENT_ID = "sleepbear_cam_01"

TOPIC_FRAME = "sleepbear/camara/frame/01"

# Índice de la cámara: 0 = cámara por defecto, 1 = segunda cámara, etc.
CAMERA_INDEX = 2

# Resolución del frame (equivalente a QVGA del ESP32)
FRAME_WIDTH  = 320
FRAME_HEIGHT = 240

# Calidad JPEG (0-100). 40 ≈ calidad moderada, tamaño reducido
# Equivale al quality(10) del ESP32 en términos de balance tamaño/calidad
JPEG_QUALITY = 100

FPS_DELAY = 2.0  # segundos entre frames

# ══════════════════════════════════════════
# MQTT
# ══════════════════════════════════════════
def conectar_mqtt() -> mqtt.Client:
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            print(f"[MQTT] Conectado a {BROKER}")
        else:
            print(f"[MQTT] Error de conexión, código: {rc}")

    cliente.on_connect = on_connect
    cliente.connect(BROKER, PORT, keepalive=60)
    cliente.loop_start()  # hilo en background para mantener la conexión viva
    return cliente

# ══════════════════════════════════════════
# CÁMARA
# ══════════════════════════════════════════
# En cam_publisher.py, reemplaza tu función por esta:
def inicializar_camara(index: int) -> cv2.VideoCapture:
    # Robado del debug: usamos el índice 1 (o el que te funcionó) y CAP_DSHOW
    cap = cv2.VideoCapture(1, cv2.CAP_DSHOW) 

    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir la cámara")

    # COMENTA O BORRA ESTAS LÍNEAS para que no fuercen el tamaño QVGA:
    # cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    print("[CAM] Cámara inicializada con la configuración exacta de Debug")
    return cap

def capturar_frame_encoded(cap):
    ret, frame = cap.read()
    if not ret:
        return None

    # BORRA O COMENTA la línea del resize para mantener el formato del debug:
    # frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

    encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
    _, buffer = cv2.imencode(".jpg", frame, encode_params)
    encoded = base64.b64encode(buffer.tobytes())
    return encoded

# ══════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════
def main():
    cliente = conectar_mqtt()
    time.sleep(1)  # esperar confirmación de conexión

    cap = inicializar_camara(CAMERA_INDEX)
    print(f"[CAM] Publicando frames cada {FPS_DELAY}s en '{TOPIC_FRAME}'...")

    frame_count = 0
    try:
        while True:
            encoded = capturar_frame_encoded(cap)
            if encoded:
                cliente.publish(TOPIC_FRAME, encoded)
                frame_count += 1
                if frame_count % 10 == 0:
                    print(f"[CAM] {frame_count} frames publicados")
            time.sleep(FPS_DELAY)

    except KeyboardInterrupt:
        print("[CAM] Detenido.")
    finally:
        cap.release()          # liberar la cámara correctamente
        cliente.loop_stop()
        cliente.disconnect()

main()