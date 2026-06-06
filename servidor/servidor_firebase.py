"""
OBJETIVO: Gestión de Firebase y Dashboard de usuario.
          Puente MQTT-Firebase para SleepBear. Recibe telemetría del
          ESP32 vía MQTT y la persiste en Firebase Realtime Database con
          timestamp. Almacena 3 tipos de eventos: Telemetría, Alertas y
          Estado de actuadores. Escucha comandos remotos del dashboard
          y los reenvía al ESP32 por MQTT para control bidireccional.
          Sin almacenamiento de imágenes — solo métricas numéricas.
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

import firebase_admin
from firebase_admin import credentials, db
import paho.mqtt.client as mqtt
import json
import threading
from datetime import datetime, timezone

# ══════════════════════════════════════════
# CONFIGURACIÓN FIREBASE
# ══════════════════════════════════════════
FIREBASE_CRED = "serviceAccountKey.json"
FIREBASE_URL  = "https://sleepbear-95f3e-default-rtdb.firebaseio.com/"  # ← cambia esto

# ══════════════════════════════════════════
# CONFIGURACIÓN MQTT
# ══════════════════════════════════════════
BROKER    = "broker.hivemq.com"
PORT      = 1883
CLIENT_ID = "sleepbear_firebase_01"

T_ESTADO   = "sleepbear/sensor/estado/01"
T_ALERTAS  = "sleepbear/sistema/alertas/01"
T_CMD_LED  = "sleepbear/comando/led/01"
T_CMD_FAN  = "sleepbear/comando/ventilador/01"
T_CMD_AUD  = "sleepbear/comando/audio/01"

# Variable global para el cliente MQTT
# Necesaria para que el hilo de Firebase pueda publicar comandos
mqtt_client_global = None

# ══════════════════════════════════════════
# INICIALIZAR FIREBASE
# ══════════════════════════════════════════
cred = credentials.Certificate(FIREBASE_CRED)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})

# ══════════════════════════════════════════
# UTILIDADES DE TIMESTAMP
# ══════════════════════════════════════════
def ts_iso():
    """Timestamp ISO 8601 en UTC para almacenar en Firebase."""
    return datetime.now(timezone.utc).isoformat()

def ts_key():
    """Clave única por timestamp para nodos Firebase.
    Evita caracteres prohibidos como . / # $ [ ]"""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

def ts_log():
    """Timestamp legible para los logs de consola."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ══════════════════════════════════════════
# TIPO 1 DE EVENTO: TELEMETRÍA
# Guarda el estado completo de sensores.
# Solo métricas numéricas — sin imágenes (privacidad).
# ══════════════════════════════════════════
def guardar_telemetria(estado):
    """Persiste telemetría en Firebase con timestamp."""
    # Filtrar None para no guardar lecturas fallidas
    registro = {k: v for k, v in estado.items() if v is not None}
    registro["ts"] = ts_iso()
    # Guardar en historial
    db.reference(f"telemetria/historial/{ts_key()}").set(registro)
    # Actualizar última lectura para el dashboard en tiempo real
    db.reference("telemetria/ultima").set(registro)
    print(f"[{ts_log()}] [FB] Telemetría guardada")

# ══════════════════════════════════════════
# TIPO 2 DE EVENTO: ALERTAS
# Guarda eventos críticos del sistema.
# ══════════════════════════════════════════
def guardar_alerta(tipo, valor, fuente="sensor"):
    """Persiste una alerta con tipo, valor y timestamp."""
    registro = {
        "tipo":   tipo,
        "valor":  valor,
        "fuente": fuente,
        "ts":     ts_iso()
    }
    db.reference(f"alertas/{ts_key()}").set(registro)
    print(f"[{ts_log()}] [FB] Alerta guardada: {tipo} = {valor}")

# ══════════════════════════════════════════
# TIPO 3 DE EVENTO: ESTADO DE ACTUADORES
# Guarda cambios en el estado de los actuadores.
# ══════════════════════════════════════════
def guardar_estado_actuador(led, ventilador):
    """Persiste el estado actual de los actuadores."""
    db.reference("actuadores/estado").set({
        "led":        led,
        "ventilador": ventilador,
        "ts":         ts_iso()
    })

# ══════════════════════════════════════════
# ESCUCHAR COMANDOS DEL DASHBOARD
# Stream en tiempo real — reacciona inmediatamente
# cuando el usuario presiona un botón en la web.
# ══════════════════════════════════════════
def escuchar_comandos_dashboard():
    """
    Suscripción stream a Firebase. Cuando el dashboard escribe
    en actuadores/comando_remoto, este método lo detecta y
    reenvía el comando al ESP32 por MQTT inmediatamente.
    Corre en un hilo separado para no bloquear el loop MQTT.
    """
    def on_cambio(event):
        cmd = event.data
        if cmd and isinstance(cmd, dict) and mqtt_client_global:
            print(f"[{ts_log()}] [FB→MQTT] Comando del dashboard: {cmd}")
            # Determinar el tópico según el tipo de comando
            if "color" in cmd:
                mqtt_client_global.publish(T_CMD_LED, json.dumps(cmd), qos=1)
            elif "activar" in cmd:
                mqtt_client_global.publish(T_CMD_FAN, json.dumps(cmd), qos=1)
            elif "accion" in cmd:
                mqtt_client_global.publish(T_CMD_AUD, json.dumps(cmd), qos=1)
            # Limpiar el nodo para no reenviar el mismo comando
            db.reference("actuadores/comando_remoto").set(None)
    db.reference("actuadores/comando_remoto").listen(on_cambio)

# ══════════════════════════════════════════
# CALLBACKS MQTT
# ══════════════════════════════════════════
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[{ts_log()}] ✅ Conectado al broker MQTT")
        client.subscribe(T_ESTADO)
        db.reference("sistema/online").set(True)
        print(f"[{ts_log()}] Firebase + MQTT activos")
        print("=" * 55)

def on_message(client, userdata, msg):
    """
    Recibe telemetría del ESP32, la guarda en Firebase
    y genera alertas si se detectan condiciones críticas.
    """
    if msg.topic != T_ESTADO:
        return
    try:
        estado = json.loads(msg.payload.decode())

        # Guardar telemetría completa (Evento tipo 1)
        guardar_telemetria(estado)

        # Generar alertas según condiciones (Evento tipo 2)
        if estado.get("hay_fiebre"):
            guardar_alerta("FIEBRE", estado.get("temperatura_bebe"), "mlx90614")
        if estado.get("llanto_detectado"):
            guardar_alerta("LLANTO", estado.get("nivel_sonido"), "ky037")
        if estado.get("cuarto_caliente"):
            guardar_alerta("CALOR",  estado.get("temperatura_cuarto"), "dht11")

        # Guardar estado de actuadores (Evento tipo 3)
        if estado.get("hay_fiebre") or estado.get("llanto_detectado"):
            guardar_estado_actuador("rojo", False)
        elif estado.get("cuarto_caliente"):
            guardar_estado_actuador("amarillo", True)
        else:
            guardar_estado_actuador("verde", False)

    except Exception as e:
        print(f"[{ts_log()}] [ERROR] {e}")

def on_disconnect(client, userdata, rc, properties=None):
    db.reference("sistema/online").set(False)
    print(f"[{ts_log()}] Desconectado")

# ══════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════
def main():
    global mqtt_client_global
    print(f"[{ts_log()}] SleepBear — Servidor Firebase")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=CLIENT_ID)
    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect
    mqtt_client_global = client

    # Iniciar hilo que escucha comandos del dashboard en tiempo real
    hilo = threading.Thread(target=escuchar_comandos_dashboard, daemon=True)
    hilo.start()

    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()

if __name__ == "__main__":
    main()
