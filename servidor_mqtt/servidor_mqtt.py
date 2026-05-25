# =============================================================================
# ARCHIVO:      servidor_mqtt.py
# PROYECTO:     SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
# INTEGRANTES:  Jacziry Berenice Aragón Guerrero  21240179
#               Juan José Cortes Íñiguez          21240173
# DESCRIPCIÓN:  Puente MQTT ↔ Firebase.
#               Se suscribe a todos los tópicos de sensores y alertas que
#               publica la ESP32, imprime cada mensaje con timestamp en
#               consola y lo reenvía a Firebase Realtime Database.
#               Actúa como capa intermedia obligatoria entre la ESP32 y
#               la base de datos, siguiendo la arquitectura del curso:
#
#               ESP32 → publica MQTT → HiveMQ (broker.hivemq.com)
#                     → servidor_mqtt.py (este script, suscrito)
#                     → imprime en consola con timestamp
#                     → persiste en Firebase Realtime Database
#
# DEPENDENCIAS: pip install paho-mqtt requests python-dotenv
# USO:          python servidor_mqtt.py
# =============================================================================

import paho.mqtt.client as mqtt
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
import os

# Cargar variables de entorno desde .env
load_dotenv()


# =============================================================================
#  CONFIGURACIÓN
# =============================================================================

# ── Broker HiveMQ público ─────────────────────────────────────────────────────
# El mismo broker al que publica la ESP32, no requiere credenciales.
BROKER_HOST = "broker.hivemq.com"
BROKER_PORT = 1883
CLIENT_ID   = "sleepbear-servidor-python"

# ── Firebase Realtime Database ────────────────────────────────────────────────
FIREBASE_URL = https://sistemas-programables-9fd09-default-rtdb.firebaseio.com/
# ── Tópicos de sensores que publica la ESP32 ─────────────────────────────────
TOPICOS_SENSORES = [
    "sleepbear/sensores/temp_bebe",
    "sleepbear/sensores/temp_cuarto",
    "sleepbear/sensores/humedad",
    "sleepbear/sensores/nivel_luz",
    "sleepbear/sensores/nivel_sonido",
]

# ── Tópicos de alertas que publica la ESP32 ───────────────────────────────────
TOPICOS_ALERTAS = [
    "sleepbear/alertas/fiebre",
    "sleepbear/alertas/cuarto_caliente",
    "sleepbear/alertas/llanto",
    "sleepbear/alertas/modo_noche",
]

# Todos los tópicos a suscribir
TOPICOS = TOPICOS_SENSORES + TOPICOS_ALERTAS


# =============================================================================
#  MAPEO: tópico MQTT → ruta en Firebase
# =============================================================================

RUTA_FIREBASE = {
    "sleepbear/sensores/temp_bebe":       "sleepbear/sensores/temp_bebe",
    "sleepbear/sensores/temp_cuarto":     "sleepbear/sensores/temp_cuarto",
    "sleepbear/sensores/humedad":         "sleepbear/sensores/humedad",
    "sleepbear/sensores/nivel_luz":       "sleepbear/sensores/nivel_luz",
    "sleepbear/sensores/nivel_sonido":    "sleepbear/sensores/nivel_sonido",
    "sleepbear/alertas/fiebre":           "sleepbear/alertas/fiebre",
    "sleepbear/alertas/cuarto_caliente":  "sleepbear/alertas/cuarto_caliente",
    "sleepbear/alertas/llanto":           "sleepbear/alertas/llanto",
    "sleepbear/alertas/modo_noche":       "sleepbear/alertas/modo_noche",
}


# =============================================================================
#  FUNCIONES AUXILIARES
# =============================================================================

def timestamp():
    """Devuelve la fecha y hora actual formateada para consola."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parsear_valor(raw: str):
    """
    Convierte el payload crudo (string) al tipo Python correcto.
    La ESP32 publica:
      - números como "36.6" o "55"
      - alertas como "SI" / "NO"
    """
    if raw.upper() == "SI":
        return True
    if raw.upper() == "NO":
        return False
    try:
        return float(raw) if "." in raw else int(raw)
    except ValueError:
        return raw   # devolver como string si no se puede convertir


def enviar_a_firebase(ruta: str, valor):
    """
    Persiste un valor en Firebase Realtime Database mediante PUT.

    Parámetros:
        ruta  — ruta relativa dentro de la base de datos (sin URL base)
        valor — dato a guardar (int, float, bool o str)

    Retorna True si la escritura fue exitosa, False si falló.
    """
    if not FIREBASE_URL:
        print("  [Firebase] ⚠  FIREBASE_URL no configurada. Revisar .env")
        return False

    url = f"{FIREBASE_URL.rstrip('/')}/{ruta}.json"
    try:
        resp = requests.put(url, data=json.dumps(valor), timeout=5)
        resp.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"  [Firebase] ✗  Error al escribir '{ruta}': {e}")
        return False


# =============================================================================
#  CALLBACKS MQTT
# =============================================================================

def al_conectar(client, userdata, flags, rc):
    """
    Se ejecuta una sola vez cuando el cliente establece conexión con el broker.
    Suscribe a todos los tópicos de la ESP32 en ese momento.
    """
    if rc == 0:
        print(f"[{timestamp()}] ✓ Conectado a HiveMQ en {BROKER_HOST}:{BROKER_PORT}")
        for topico in TOPICOS:
            client.subscribe(topico)
            print(f"  → Suscrito a: {topico}")
        print("-" * 60)
    else:
        print(f"[{timestamp()}] ✗ Fallo de conexión. Código de error: {rc}")


def al_desconectar(client, userdata, rc):
    """Se ejecuta si el cliente pierde la conexión con el broker."""
    print(f"\n[{timestamp()}] ✗ Desconectado del broker (rc={rc}). Reconectando...")


def al_recibir_mensaje(client, userdata, msg):
    """
    Callback principal. Se ejecuta cada vez que llega un mensaje MQTT.

    Flujo:
      1. Decodifica el payload de bytes a string.
      2. Imprime tópico, valor y timestamp en consola.
      3. Parsea el valor al tipo correcto (float, int, bool).
      4. Envía el valor a Firebase en la ruta correspondiente.
    """
    topico  = msg.topic
    raw     = msg.payload.decode("utf-8").strip()
    valor   = parsear_valor(raw)
    ts      = timestamp()

    # ── Imprimir en consola con timestamp (evidencia requerida por el curso) ─
    print(f"[{ts}]  {topico}")
    print(f"         valor crudo : {raw!r}")
    print(f"         valor parseado: {valor!r}  ({type(valor).__name__})")

    # ── Reenviar a Firebase ──────────────────────────────────────────────────
    ruta = RUTA_FIREBASE.get(topico)
    if ruta:
        ok = enviar_a_firebase(ruta, valor)
        estado = "✓ Firebase OK" if ok else "✗ Firebase FALLO"
        print(f"         {estado}")
    else:
        print(f"         [WARN] Tópico sin ruta Firebase mapeada.")

    print()   # línea en blanco para separar mensajes


# =============================================================================
#  PUNTO DE ENTRADA
# =============================================================================

def main():
    print("=" * 60)
    print("  SleepBear — Puente MQTT ↔ Firebase")
    print("  Broker   :", BROKER_HOST, ":", BROKER_PORT)
    print("  Firebase :", FIREBASE_URL or "NO CONFIGURADA")
    print("=" * 60)
    print()

    cliente = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    cliente.on_connect    = al_conectar
    cliente.on_disconnect = al_desconectar
    cliente.on_message    = al_recibir_mensaje

    try:
        cliente.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    except ConnectionRefusedError:
        print(f"[ERROR] No se pudo conectar a HiveMQ en {BROKER_HOST}:{BROKER_PORT}")
        print("        Verifica tu conexión a internet.")
        return

    print("Esperando mensajes de la ESP32... (Ctrl+C para salir)\n")

    try:
        # loop_forever() bloquea aquí y llama a los callbacks automáticamente.
        # También gestiona reconexiones ante caídas de red.
        cliente.loop_forever()
    except KeyboardInterrupt:
        print(f"\n[{timestamp()}] Servidor detenido por el usuario.")
        cliente.disconnect()


if __name__ == "__main__":
    main()
