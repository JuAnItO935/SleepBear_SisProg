"""
OBJETIVO: Detección de postura del bebé en tiempo real.
          Soporta tres fuentes de video:
            1. Webcam USB/integrada (índice OpenCV)
            2. Stream IP por HTTP (para webcam conectada a powerbank en red local)
            3. RTSP

          CORRECCIÓN v2:
            • Parámetro MODO_DETECCION: "frontal" | "cenital" | "auto"
            • Parámetro FUENTE_VIDEO: índice int ó URL string
            • Si FUENTE_VIDEO es una URL (http/rtsp), conecta por IP
            • Tecla 'm' alterna entre modos en tiempo real
            • Tecla 'c' / 'f' fuerza modo cenital / frontal

FUENTE POR IP (respuesta a corrección 5):
  La webcam A03 es USB pura (sin WiFi). Para usarla desde una powerbank
  y enviarla por red necesitas un intermediario. Opciones:
    A) Conecta la webcam USB a una Raspberry Pi Zero W / laptop ligera
       y corre un servidor de stream:
         pip install flask opencv-python
         python ip_cam_server.py   ← ver archivo adjunto
       Luego pon FUENTE_VIDEO = "http://192.168.x.x:5000/video"

    B) Usa la app "IP Webcam" (Android) o "EpocCam" (iOS) en un celular
       como cámara de red. FUENTE_VIDEO = "http://192.168.x.x:8080/video"

    C) Si tienes una ESP32-CAM (no la A03): usa cam_publisher.py en MQTT.

INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

import cv2
import paho.mqtt.client as mqtt
import json
from datetime import datetime
from detector_postura import detectar_postura, anotar_frame

# ══════════════════════════════════════════
# CONFIGURACIÓN MQTT
# ══════════════════════════════════════════
BROKER    = "broker.hivemq.com"
PORT      = 1883
CLIENT_ID = "sleepbear_webcam_ia_01"

T_CMD_LED = "sleepbear/comando/led/01"
T_CMD_AUD = "sleepbear/comando/audio/01"

# ══════════════════════════════════════════
# CONFIGURACIÓN DE VIDEO
# ══════════════════════════════════════════
# Webcam USB local: usa un entero (0 = integrada, 1, 2 = externa)
# Stream IP:        usa la URL, ej: "http://192.168.1.100:5000/video"
#                   o RTSP:          "rtsp://192.168.1.100:8554/stream"
FUENTE_VIDEO = 0       # ← cambia a URL string para IP stream

# Modo de detección:
#   "frontal"  → Haar Cascade (webcam de frente al bebé)
#   "cenital"  → segmentación de piel (cámara desde arriba)
#   "auto"     → prueba frontal primero, cae a cenital si no detecta
MODO_DETECCION = "auto"

ANALIZAR_CADA = 5   # analizar 1 de cada N frames


def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def pub(client, topic, data):
    client.publish(topic, json.dumps(data), qos=1)
    modulo = topic.split('/')[2].upper()
    print(f"  [→ CMD] {modulo}: {json.dumps(data)}")


def abrir_fuente(fuente):
    """
    Abre la fuente de video: índice entero (USB) o URL (IP stream).
    Para streams IP: OpenCV intenta conectarse a la URL directamente.
    Si falla, imprime instrucciones.
    """
    if isinstance(fuente, str):
        print(f"[CAM] Conectando a stream IP: {fuente}")
        cap = cv2.VideoCapture(fuente)
    else:
        # Intentar con DirectShow en Windows (más estable para webcams USB)
        cap = cv2.VideoCapture(fuente, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(fuente)

    if not cap.isOpened():
        if isinstance(fuente, str):
            print(f"[ERROR] No se pudo conectar al stream: {fuente}")
            print("        Opciones para conectar la webcam A03 por IP:")
            print("        1. Conecta la webcam a una Raspberry Pi / laptop")
            print("           y corre ip_cam_server.py en esa máquina.")
            print("        2. Usa una app de cámara IP en un celular.")
            print("        3. Verifica que ambos dispositivos estén en la")
            print("           misma red WiFi que el servidor de IA.")
        else:
            print(f"[ERROR] No se pudo abrir la cámara (índice={fuente})")
            print("        Cambia FUENTE_VIDEO a 1 si tienes webcam externa.")
        return None
    return cap


def main():
    # ── Conectar MQTT ─────────────────────────────────────────────────────────
    print(f"[{ts()}] Conectando al broker MQTT...")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_start()
    print(f"[{ts()}] ✅ Conectado a {BROKER}")

    # ── Inicializar video ─────────────────────────────────────────────────────
    cap = abrir_fuente(FUENTE_VIDEO)
    if cap is None:
        client.loop_stop()
        client.disconnect()
        return

    tipo_fuente = "IP stream" if isinstance(FUENTE_VIDEO, str) else f"cámara #{FUENTE_VIDEO}"
    print(f"[{ts()}] ✅ Video iniciado ({tipo_fuente})")
    print(f"[{ts()}] SleepBear IA activo — Modo: {MODO_DETECCION.upper()}")
    print(f"[{ts()}] Teclas: q=salir  s=screenshot  m=ciclar modo  c=cenital  f=frontal")
    print("=" * 55)

    frame_count    = 0
    ultima_postura = None
    screenshot_num = 0
    modo_actual    = MODO_DETECCION

    while True:
        ret, frame = cap.read()
        if not ret:
            # Para streams IP, intentar reconectar
            print(f"[{ts()}] [WARN] Frame fallido, reintentando...")
            if isinstance(FUENTE_VIDEO, str):
                cap.release()
                cap = abrir_fuente(FUENTE_VIDEO)
                if cap is None:
                    break
            else:
                break
            continue

        frame_count += 1

        # Analizar cada N frames
        if frame_count % ANALIZAR_CADA == 0:
            postura = detectar_postura(frame, modo=modo_actual)

            if postura != ultima_postura:
                print(f"[{ts()}] [IA] Postura: {postura}  (modo={modo_actual})")

                if postura == "RIESGO":
                    print(f"[{ts()}] ⚠️  RIESGO DETECTADO")
                    pub(client, T_CMD_LED, {"color": "rojo"})
                    pub(client, T_CMD_AUD, {"accion": "reproducir", "pista": 1})

                elif postura == "SEGURO":
                    pub(client, T_CMD_LED, {"color": "verde"})

                ultima_postura = postura

        # Mostrar frame anotado
        frame_vis = anotar_frame(frame.copy(),
                                 ultima_postura or "INDETERMINADO",
                                 modo=modo_actual)

        # Info de modo en pantalla
        cv2.putText(frame_vis, f"[{modo_actual.upper()}]", (10, frame_vis.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        cv2.imshow("SleepBear — Deteccion de Postura", frame_vis)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord('q'):
            break
        elif tecla == ord('s'):
            nombre = f"../evidencias/webcam_resultado_{screenshot_num}.jpg"
            cv2.imwrite(nombre, frame_vis)
            print(f"[{ts()}] Screenshot: {nombre}")
            screenshot_num += 1
        elif tecla == ord('m'):
            # Ciclar entre modos
            modos = ["auto", "frontal", "cenital"]
            idx = modos.index(modo_actual)
            modo_actual = modos[(idx + 1) % len(modos)]
            print(f"[{ts()}] Modo cambiado a: {modo_actual.upper()}")
        elif tecla == ord('c'):
            modo_actual = "cenital"
            print(f"[{ts()}] Modo: CENITAL")
        elif tecla == ord('f'):
            modo_actual = "frontal"
            print(f"[{ts()}] Modo: FRONTAL")

    cap.release()
    cv2.destroyAllWindows()
    client.loop_stop()
    client.disconnect()
    print(f"\n[{ts()}] Sistema detenido.")


if __name__ == "__main__":
    main()

