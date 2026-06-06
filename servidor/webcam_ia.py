"""
OBJETIVO: Integración de IA para detección de postura del bebé en tiempo
          real usando la webcam de la computadora y MediaPipe Pose.
          Captura frames, detecta el esqueleto corporal y publica comandos
          MQTT al ESP32 si detecta posición de riesgo (boca abajo).
          Pipeline: Webcam → MediaPipe Pose → Python → MQTT → ESP32.
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

# Modelo: MediaPipe Pose — detección de esqueleto corporal
# Librería: MediaPipe + OpenCV + paho-mqtt
# Precisión aproximada: 88-92% en iluminación normal
# Predicción: SEGURO (boca arriba) / RIESGO (boca abajo) / INDETERMINADO

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
# CONFIGURACIÓN WEBCAM
# 0 = webcam integrada | 1 = webcam externa
# ══════════════════════════════════════════
WEBCAM_INDEX  = 2
ANALIZAR_CADA = 5   # analizar 1 de cada 5 frames (balance CPU vs velocidad)

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def pub(client, topic, data):
    """Publica comando MQTT con QoS 1 e imprime en consola."""
    client.publish(topic, json.dumps(data), qos=1)
    modulo = topic.split('/')[2].upper()
    print(f"  [→ CMD] {modulo}: {json.dumps(data)}")

def main():
    # ── Conectar MQTT ─────────────────────────────────────────────
    print(f"[{ts()}] Conectando al broker MQTT...")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=CLIENT_ID)
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_start()   # loop en hilo separado — no bloquea la webcam
    print(f"[{ts()}] ✅ Conectado a {BROKER}")

    # ── Inicializar webcam ────────────────────────────────────────
    cap = cv2.VideoCapture(WEBCAM_INDEX)
    if not cap.isOpened():
        print("[ERROR] No se pudo abrir la webcam.")
        print("        Cambia WEBCAM_INDEX a 1 si tienes webcam externa.")
        return

    print(f"[{ts()}] ✅ Webcam iniciada")
    print(f"[{ts()}] SleepBear IA activo — MediaPipe Pose")
    print(f"[{ts()}] Presiona 'q' para salir | 's' para guardar screenshot")
    print("=" * 55)

    frame_count    = 0
    ultima_postura = None
    screenshot_num = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] No se pudo leer el frame.")
            break

        frame_count += 1

        # Analizar cada N frames
        if frame_count % ANALIZAR_CADA == 0:
            postura = detectar_postura(frame)

            # Solo publicar si la postura cambió — evita spam al broker
            if postura != ultima_postura:
                print(f"[{ts()}] [IA] Postura: {postura}")

                if postura == "RIESGO":
                    print(f"[{ts()}] ⚠️  RIESGO DETECTADO")
                    pub(client, T_CMD_LED, {"color": "rojo"})
                    pub(client, T_CMD_AUD, {"accion": "reproducir", "pista": 1})

                elif postura == "SEGURO":
                    pub(client, T_CMD_LED, {"color": "verde"})

                ultima_postura = postura

        # Mostrar frame con esqueleto y resultado anotado
        frame_vis = anotar_frame(frame.copy(),
                                 ultima_postura or "INDETERMINADO")
        cv2.imshow("SleepBear — Deteccion de Postura (MediaPipe)", frame_vis)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord('q'):
            break
        elif tecla == ord('s'):
            # Guardar screenshot como evidencia
            nombre = f"../evidencias/webcam_resultado_{screenshot_num}.jpg"
            cv2.imwrite(nombre, frame_vis)
            print(f"[{ts()}] Screenshot guardado: {nombre}")
            screenshot_num += 1

    # Limpieza
    cap.release()
    cv2.destroyAllWindows()
    client.loop_stop()
    client.disconnect()
    print(f"\n[{ts()}] Sistema detenido.")

if __name__ == "__main__":
    main()