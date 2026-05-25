"""
OBJETIVO: Script principal de SleepBear con integración MQTT completa.
          Publica la telemetría de TODOS los sensores (MLX90614, DHT11,
          LDR, KY-038) y recibe comandos para controlar TODOS los
          actuadores (LED RGB, ventilador DC, DFPlayer Mini) respetando
          estrictamente la capa HAL de dispositivos.py.
          Incorpora correcciones de hardware: frecuencia I2C explícita,
          filtro de llanto con muestras múltiples.
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

import time
import ujson
import network
from umqtt.simple import MQTTClient
from dispositivos import CajaDeSensores, CajaDeActuadores

# ═══════════════════════════════════════════════════════════
# CONFIGURACIÓN — Edita solo estas líneas
# ═══════════════════════════════════════════════════════════
WIFI_SSID     = "Megcable_2.4G_AA78"     # ← tu red 2.4 GHz
WIFI_PASSWORD = "MCT6FQYb"     # ← tu contraseña
BROKER        = "broker.hivemq.com"    # broker público gratuito
CLIENT_ID     = "sleepbear_esp32_01"

# ═══════════════════════════════════════════════════════════
# TÓPICOS MQTT — Formato: proyecto/tipo/modulo/id
# ═══════════════════════════════════════════════════════════
# Publicación — ESP32 envía datos al servidor
T_ESTADO   = b"sleepbear/sensor/estado/01"
T_MLX      = b"sleepbear/sensor/mlx90614/01"
T_DHT      = b"sleepbear/sensor/dht11/01"
T_LDR      = b"sleepbear/sensor/ldr/01"
T_MIC      = b"sleepbear/sensor/microfono/01"
T_ACT_LED  = b"sleepbear/actuador/led/01"
T_ACT_FAN  = b"sleepbear/actuador/ventilador/01"
T_ACT_AUD  = b"sleepbear/actuador/audio/01"
# Suscripción — ESP32 recibe comandos del servidor
T_CMD_LED  = b"sleepbear/comando/led/01"
T_CMD_FAN  = b"sleepbear/comando/ventilador/01"
T_CMD_AUD  = b"sleepbear/comando/audio/01"
T_CMD_SIS  = b"sleepbear/comando/sistema/01"

# ═══════════════════════════════════════════════════════════
# INSTANCIAS HAL
# Toda interacción con hardware pasa SIEMPRE por estas clases.
# Nunca llamar Pin(), ADC(), I2C(), PWM() directamente aquí.
# ═══════════════════════════════════════════════════════════
sensores   = CajaDeSensores()
actuadores = CajaDeActuadores()

# ═══════════════════════════════════════════════════════════
# WIFI
# ═══════════════════════════════════════════════════════════
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("[WIFI] Conectando a:", WIFI_SSID)
        print("       (Solo redes 2.4 GHz — el ESP32 no soporta 5 GHz)")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        intentos = 0
        while not wlan.isconnected() and intentos < 20:
            time.sleep(0.5)
            intentos += 1
            print(".", end="")
    if wlan.isconnected():
        print("\n[WIFI] Conectado. IP:", wlan.ifconfig()[0])
        return True
    print("\n[WIFI] ERROR — verifica SSID/password y que sea red 2.4 GHz")
    return False

# ═══════════════════════════════════════════════════════════
# CALLBACK DE COMANDOS
# Se ejecuta cuando el servidor envía un comando.
# DELEGA SIEMPRE a la HAL — nunca acceso directo a hardware.
# ═══════════════════════════════════════════════════════════
def on_comando(topic, payload):
    try:
        t   = topic.decode()
        cmd = ujson.loads(payload)
        print("[CMD recibido]", t, "→", cmd)

        if t == "sleepbear/comando/led/01":
            c = cmd.get("color", "")
            # HAL gestiona los valores PWM internamente
            if c == "rojo":     actuadores.indicar_alerta()
            elif c == "amarillo": actuadores.indicar_atencion()
            elif c == "verde":  actuadores.indicar_todo_bien()
            elif c == "azul":   actuadores.calmar_llanto()

        elif t == "sleepbear/comando/ventilador/01":
            # HAL gestiona el transistor NPN internamente
            if cmd.get("activar"):  actuadores.activar_ventilador()
            else:                   actuadores.desactivar_ventilador()

        elif t == "sleepbear/comando/audio/01":
            a = cmd.get("accion", "")
            # HAL gestiona el protocolo UART al DFPlayer internamente
            if a == "reproducir":
                actuadores.reproducir_musica_cuna(cmd.get("pista", 1))
            elif a == "detener":  actuadores.detener_musica()
            elif a == "volumen":  actuadores.ajustar_volumen(cmd.get("nivel", 15))

        elif t == "sleepbear/comando/sistema/01":
            if cmd.get("modo") == "seguro":    actuadores.estado_seguro()
            elif cmd.get("modo") == "nocturno": actuadores.modo_nocturno()

    except Exception as e:
        print("[ERROR on_comando]", e)

# ═══════════════════════════════════════════════════════════
# PUBLICAR TELEMETRÍA
# Publica en tópicos individuales Y en el tópico de estado
# completo para que el servidor tenga el panorama completo.
# ═══════════════════════════════════════════════════════════
def publicar_telemetria(cli, estado):
    # Estado completo en un solo tópico (más eficiente)
    cli.publish(T_ESTADO, ujson.dumps(estado))
    # Tópicos individuales por sensor (para MQTT Explorer y diagnóstico)
    cli.publish(T_MLX,
        ujson.dumps({"temp_bebe": estado["temperatura_bebe"],
                     "hay_fiebre": estado["hay_fiebre"]}))
    cli.publish(T_DHT,
        ujson.dumps({"temp_cuarto": estado["temperatura_cuarto"],
                     "humedad": estado["humedad_cuarto"]}))
    cli.publish(T_LDR,
        ujson.dumps({"nivel_luz": estado["nivel_luz"],
                     "esta_oscuro": estado["esta_oscuro"]}))
    cli.publish(T_MIC,
        ujson.dumps({"nivel_sonido": estado["nivel_sonido"],
                     "llanto_detectado": estado["llanto_detectado"]}))
    # Estado actual de los actuadores
    cli.publish(T_ACT_FAN,
        ujson.dumps({"activo": estado["cuarto_caliente"]}))

# ═══════════════════════════════════════════════════════════
# BUCLE PRINCIPAL
# ═══════════════════════════════════════════════════════════
def main():
    if not conectar_wifi():
        return

    cli = MQTTClient(CLIENT_ID, BROKER, keepalive=60)
    cli.set_callback(on_comando)
    cli.connect()
    # Suscribirse a los 4 tópicos de comando
    cli.subscribe(T_CMD_LED)
    cli.subscribe(T_CMD_FAN)
    cli.subscribe(T_CMD_AUD)
    cli.subscribe(T_CMD_SIS)
    print("[MQTT] Conectado a", BROKER)
    print("[SleepBear] Sistema activo — publicando cada 2 s")

    try:
        while True:
            # check_msg() revisa si llegó algún comando (NO bloqueante)
            # Si se usara wait_msg() el bucle se detendría esperando
            cli.check_msg()

            # Una sola llamada HAL obtiene todos los sensores
            # detectar_llanto() internamente toma 5 muestras × 40ms
            # evitando falsas alarmas por sonidos puntuales
            estado = sensores.obtener_estado_completo()

            # Publicar telemetría completa en MQTT
            publicar_telemetria(cli, estado)

            # Log en consola de Thonny para verificación
            print("[SENS] T_bebé={} | T_cuarto={} | Llanto={} | Fiebre={}".format(
                estado["temperatura_bebe"], estado["temperatura_cuarto"],
                estado["llanto_detectado"], estado["hay_fiebre"]))

            # Lógica local de respaldo (funciona aunque el servidor no responda)
            if estado["llanto_detectado"]:
                actuadores.indicar_alerta()
                actuadores.reproducir_musica_cuna()
            elif estado["hay_fiebre"]:
                actuadores.activar_alerta_fiebre()
            elif estado["cuarto_caliente"]:
                actuadores.indicar_atencion()
                actuadores.activar_ventilador()
            else:
                actuadores.desactivar_ventilador()
                actuadores.detener_musica()
                actuadores.indicar_todo_bien()

            if estado["esta_oscuro"]:
                actuadores.modo_nocturno()
            else:
                actuadores.ajustar_volumen(15)

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n[SISTEMA] Apagando...")
        actuadores.estado_seguro()
        cli.disconnect()
        print("[SISTEMA] Apagado correctamente.")

main()
