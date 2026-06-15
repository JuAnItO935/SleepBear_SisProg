"""
servidor_firebase.py — Puente MQTT→Firebase para SleepBear
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés

BUGS CORREGIDOS:
  1. FIREBASE SOLO MOSTRABA EL RGB: guardar_estado_actuador() solo escribía
     led y ventilador, nunca temperatura, humedad, sonido, etc. El dashboard
     leía "telemetria/ultima" pero el servidor solo escribía "actuadores/estado".
     Ahora guardar_telemetria() escribe TODOS los sensores en "telemetria/ultima"
     que es exactamente el nodo que escucha el dashboard.

  2. CONTADORES DE ALERTAS FALTANTES: el dashboard espera "alertas/contadores"
     con claves LLANTO, FIEBRE, CALOR. El servidor antiguo nunca los escribía,
     los contadores siempre marcaban 0. Ahora se incrementan con cada alerta.

  3. HISTORIAL EN RUTA INCORRECTA: el servidor escribía en "alertas/{ts_key()}"
     (ruta plana) pero el dashboard busca "alertas/historial/{clave}".
     Corregido en guardar_alerta().
"""

import firebase_admin
from firebase_admin import credentials, db
import paho.mqtt.client as mqtt
import json
import threading
from datetime import datetime, timezone

# ══════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════
FIREBASE_CRED = "serviceAccountKey.json"
FIREBASE_URL  = "https://sleepbear-95f3e-default-rtdb.firebaseio.com/"

BROKER    = "broker.hivemq.com"
PORT      = 1883
CLIENT_ID = "sleepbear_firebase_bridge"

T_ESTADO      = "sleepbear/sensor/estado/01"
T_ACTUADORES  = "sleepbear/actuadores/estado/01"
T_CMD_LED     = "sleepbear/comando/led/01"
T_CMD_FAN     = "sleepbear/comando/ventilador/01"
T_CMD_AUD     = "sleepbear/comando/audio/01"

mqtt_client_global = None

# ══════════════════════════════════════════
# INICIALIZAR FIREBASE
# ══════════════════════════════════════════
cred = credentials.Certificate(FIREBASE_CRED)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})

# ══════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════
def ts_iso():
    return datetime.now(timezone.utc).isoformat()

def ts_key():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

def ts_log():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ══════════════════════════════════════════
# GUARDAR TELEMETRÍA
# FIX: ahora escribe en "telemetria/ultima" que es lo que lee el dashboard.
# También escribe el historial con timestamp para las gráficas.
# ══════════════════════════════════════════
def guardar_telemetria(estado):
    registro = {k: v for k, v in estado.items() if v is not None}
    registro["ts"] = ts_iso()

    # FIX: esta es la ruta que el dashboard escucha con onValue()
    db.reference("telemetria/ultima").set(registro)

    # Historial opcional para futuras gráficas (limitado a 500 entradas)
    db.reference(f"telemetria/historial/{ts_key()}").set(registro)
    print(f"[{ts_log()}] [FB] Telemetría guardada — {len(registro)} campos")


# ══════════════════════════════════════════
# GUARDAR ALERTA
# FIX: ruta corregida a "alertas/historial/{key}" + contadores incrementales
# ══════════════════════════════════════════
def guardar_alerta(tipo, valor, fuente="sensor"):
    registro = {
        "tipo":   tipo,
        "valor":  valor,
        "fuente": fuente,
        "ts":     ts_iso()
    }

    # FIX HISTORIAL: el dashboard busca alertas/historial/*, no alertas/*
    db.reference(f"alertas/historial/{ts_key()}").set(registro)

    # FIX CONTADORES: incrementar el contador correspondiente
    ref_contador = db.reference(f"alertas/contadores/{tipo}")
    actual = ref_contador.get() or 0
    ref_contador.set(actual + 1)

    print(f"[{ts_log()}] [FB] Alerta: {tipo} = {valor} (total: {actual+1})")


# ══════════════════════════════════════════
# GUARDAR ESTADO ACTUADOR (solo LED para el dashboard)
# ══════════════════════════════════════════
def guardar_estado_actuador(led, ventilador):
    db.reference("actuadores/estado").set({
        "led":        led,
        "ventilador": ventilador,
        "ts":         ts_iso()
    })


# ══════════════════════════════════════════
# ESCUCHAR COMANDOS DEL DASHBOARD → MQTT
# ══════════════════════════════════════════
def escuchar_comandos_dashboard():
    def on_cambio(event):
        cmd = event.data
        if not cmd or not isinstance(cmd, dict) or not mqtt_client_global:
            return

        print(f"[{ts_log()}] [FB→MQTT] Comando: {cmd}")

        if "color" in cmd:
            mqtt_client_global.publish(T_CMD_LED, json.dumps(cmd), qos=1)
        elif "activar" in cmd:
            mqtt_client_global.publish(T_CMD_FAN, json.dumps(cmd), qos=1)
        elif "accion" in cmd:
            mqtt_client_global.publish(T_CMD_AUD, json.dumps(cmd), qos=1)

        db.reference("actuadores/comando_remoto").delete()

    db.reference("actuadores/comando_remoto").listen(on_cambio)


# ══════════════════════════════════════════
# CALLBACKS MQTT
# ══════════════════════════════════════════
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[{ts_log()}] ✅ Conectado al broker MQTT")
        client.subscribe(T_ESTADO)
        client.subscribe(T_ACTUADORES)
        db.reference("sistema/online").set(True)
        print("=" * 55)

def on_message(client, userdata, msg):
    # ── Estado de actuadores (LED, ventilador, música) ────
    if msg.topic == T_ACTUADORES:
        try:
            estado = json.loads(msg.payload.decode())
            estado["ts"] = ts_iso()
            db.reference("actuadores/estado").set(estado)
            print(f"[{ts_log()}] [FB] Actuadores: {estado}")
        except Exception as e:
            print(f"[{ts_log()}] [ERROR actuadores] {e}")
        return

    # ── Telemetría de sensores ────────────────────────────
    if msg.topic != T_ESTADO:
        return
    try:
        estado = json.loads(msg.payload.decode())

        # FIX: guardar TODOS los sensores en telemetria/ultima
        guardar_telemetria(estado)

        # Generar alertas si corresponde
        if estado.get("hay_fiebre"):
            guardar_alerta("FIEBRE", estado.get("temperatura_bebe"), "mlx90614")
        if estado.get("llanto_detectado"):
            guardar_alerta("LLANTO", estado.get("nivel_sonido"), "ky038")
        if estado.get("cuarto_caliente"):
            guardar_alerta("CALOR",  estado.get("temperatura_cuarto"), "dht11")

        # Actualizar estado del LED para la tarjeta del dashboard
        if estado.get("hay_fiebre") or estado.get("llanto_detectado"):
            guardar_estado_actuador("rojo", False)
        elif estado.get("cuarto_caliente"):
            guardar_estado_actuador("amarillo", True)
        else:
            guardar_estado_actuador("verde", False)

    except Exception as e:
        print(f"[{ts_log()}] [ERROR] {e}")

def on_disconnect(client, userdata, disconnect_flags, rc, properties=None):
    db.reference("sistema/online").set(False)
    print(f"[{ts_log()}] Desconectado (rc={rc})")


# ══════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════
def main():
    global mqtt_client_global
    print(f"[{ts_log()}] SleepBear — Servidor Firebase iniciando...")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect
    mqtt_client_global   = client

    # Hilo para escuchar comandos del dashboard
    hilo = threading.Thread(target=escuchar_comandos_dashboard, daemon=True)
    hilo.start()

    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()

if __name__ == "__main__":
    main()