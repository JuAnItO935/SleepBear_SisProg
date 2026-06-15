"""
OBJETIVO: Servidor Python con IA para SleepBear. Recibe frames de la
          ESP32-CAM vía MQTT o de la webcam USB publicada por cam_publisher.py,
          aplica detección de postura del bebé con OpenCV y publica comandos
          de alerta si detecta posición de riesgo (boca abajo = riesgo SMSL).

CORRECCIÓN v2:
  • Acepta modo de detección en el payload JSON: {"modo": "cenital"} o
    {"modo": "frontal"} — útil para cambiar el modo desde el dashboard.
  • Modo por defecto configurable con MODO_DEFAULT.
  • Usa detector_postura.py v2 que soporta ambos modos.

INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

import paho.mqtt.client as mqtt
import json
import base64
import numpy as np
import cv2
from datetime import datetime, timezone
from detector_postura import detectar_postura
import firebase_admin
from firebase_admin import credentials, db as fb_db
import os

# ── Inicializar Firebase ──────────────────────────────────────────────────────
_firebase_ok  = False
_FIREBASE_CRED = os.path.join(os.path.dirname(__file__), "serviceAccountKey.json")
_FIREBASE_URL  = "https://sleepbear-95f3e-default-rtdb.firebaseio.com/"

try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(_FIREBASE_CRED)
        firebase_admin.initialize_app(cred, {"databaseURL": _FIREBASE_URL})
    _firebase_ok = True
    print("[IA] Firebase conectado")
except Exception as _e:
    print(f"[IA] Firebase no disponible: {_e} — solo MQTT activo")

# ══════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════
BROKER    = "broker.hivemq.com"
PORT      = 1883
CLIENT_ID = "sleepbear_ia_01"

# Tópicos
T_CAMARA = "sleepbear/camara/frame/01"
T_CMD_LED = "sleepbear/comando/led/01"
T_CMD_AUD = "sleepbear/comando/audio/01"
T_CMD_SIS = "sleepbear/comando/sistema/01"

# Modo de detección por defecto:
#   "auto"    → prueba frontal, cae a cenital si no detecta cara
#   "frontal" → solo Haar Cascade (ESP32-CAM o webcam de frente)
#   "cenital" → solo segmentación de piel (cámara desde arriba)
MODO_DEFAULT = "auto"

# ══════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════
def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def escribir_postura_firebase(postura, modo):
    if not _firebase_ok:
        return
    try:
        fb_db.reference("ia/postura").set({
            "resultado": postura,
            "modo": modo,
            "ts": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        print(f"[IA] Firebase write error: {e}")


def pub(client, topic, data):
    client.publish(topic, json.dumps(data), qos=1)
    print(f"  [→ CMD] {topic.split('/')[2].upper()}: {json.dumps(data)}")


# ══════════════════════════════════════════
# CALLBACKS MQTT
# ══════════════════════════════════════════
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[{ts()}] ✅ Conectado al broker")
        client.subscribe(T_CAMARA)
        client.subscribe(T_CMD_SIS)   # para recibir cambio de modo
        print(f"[{ts()}] Suscrito a {T_CAMARA} y {T_CMD_SIS}")
        print(f"[{ts()}] Modo de detección: {MODO_DEFAULT.upper()}")
        print("=" * 55)


def on_message(client, userdata, msg):
    global MODO_DEFAULT

    # ── Comandos de sistema (cambio de modo desde dashboard) ─────────────────
    if msg.topic == T_CMD_SIS:
        try:
            cmd = json.loads(msg.payload)
            if "modo" in cmd and cmd["modo"] in ("auto", "frontal", "cenital"):
                MODO_DEFAULT = cmd["modo"]
                print(f"[{ts()}] Modo cambiado a: {MODO_DEFAULT.upper()}")
        except Exception:
            pass
        return

    # ── Frame de cámara ───────────────────────────────────────────────────────
    if msg.topic != T_CAMARA:
        return

    try:
        # El payload puede ser solo base64, o JSON con modo + frame
        payload = msg.payload
        modo = MODO_DEFAULT

        # Intentar parsear como JSON primero (payload enriquecido)
        try:
            data = json.loads(payload)
            if isinstance(data, dict) and "frame" in data:
                jpg_bytes = base64.b64decode(data["frame"])
                modo = data.get("modo", MODO_DEFAULT)
            else:
                jpg_bytes = base64.b64decode(payload)
        except Exception:
            # Payload es solo base64 puro
            jpg_bytes = base64.b64decode(payload)

        # Decodificar imagen
        np_arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
        frame  = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            print(f"[{ts()}] [WARN] Frame inválido, ignorando")
            return

        print(f"[{ts()}] Frame recibido: {frame.shape}, modo={modo}")

        # Correr detección
        postura = detectar_postura(frame, modo=modo)
        print(f"[{ts()}] [IA] Postura: {postura}")

        # Publicar en Firebase
        escribir_postura_firebase(postura, modo)

        # Tomar decisión
        if postura == "RIESGO":
            print(f"[{ts()}] ⚠️  RIESGO DETECTADO — activando alerta")
            pub(client, T_CMD_LED, {"color": "rojo"})
            pub(client, T_CMD_AUD, {"accion": "reproducir", "pista": 1})
        elif postura == "SEGURO":
            pub(client, T_CMD_LED, {"color": "verde"})
        # INDETERMINADO → no enviar comando

    except Exception as e:
        print(f"[{ts()}] [ERROR] {e}")


# ══════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════
def main():
    print(f"[{ts()}] SleepBear — Servidor IA")
    print(f"[{ts()}] Modo por defecto: {MODO_DEFAULT.upper()}")
    print(f"[{ts()}] Para cambiar modo publica en '{T_CMD_SIS}':")
    print(f'         {{"modo": "cenital"}} | {{"modo": "frontal"}} | {{"modo": "auto"}}')

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()

