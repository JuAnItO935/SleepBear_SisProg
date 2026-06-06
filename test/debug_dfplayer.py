"""
OBJETIVO: Script de diagnóstico para el DFPlayer Mini.
          Prueba alimentación, comunicación UART y reproducción
          sin depender de MQTT ni de otros sensores.
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

from machine import Pin, UART
import time

# ══════════════════════════════════════════
# PINES — igual que en dispositivos.py
# ══════════════════════════════════════════
PIN_TX = 13   # ESP32 TX → DFPlayer RX  (con resistencia 1kΩ)
PIN_RX = 14   # ESP32 RX ← DFPlayer TX
LED_ONBOARD = Pin(2, Pin.OUT)  # LED azul de la ESP32 para indicar estado

# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════
def parpadear(n=3, ms=150):
    """Parpadea el LED onboard de la ESP32 para indicar pasos."""
    for _ in range(n):
        LED_ONBOARD.on()
        time.sleep_ms(ms)
        LED_ONBOARD.off()
        time.sleep_ms(ms)

def checksum(cmd, param):
    suma = 0xFF + 0x06 + cmd + 0x00 + ((param >> 8) & 0xFF) + (param & 0xFF)
    return (-(suma)) & 0xFFFF

def enviar(uart, cmd, param=0):
    """Construye y envía el paquete de 10 bytes al DFPlayer."""
    msb = (param >> 8) & 0xFF
    lsb = param & 0xFF
    chk = checksum(cmd, param)
    paquete = bytes([
        0x7E, 0xFF, 0x06, cmd, 0x00,
        msb, lsb,
        (chk >> 8) & 0xFF,
        chk & 0xFF,
        0xEF
    ])
    uart.write(paquete)
    print(f"  → Enviado: {[hex(b) for b in paquete]}")
    return paquete

def leer_respuesta(uart, timeout_ms=500):
    """Lee la respuesta del DFPlayer si la hay."""
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    buf = b""
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        if uart.any():
            buf += uart.read(uart.any())
        time.sleep_ms(20)
    if buf:
        print(f"  ← Respuesta: {[hex(b) for b in buf]}")
        return buf
    else:
        print("  ← Sin respuesta del DFPlayer")
        return None

# ══════════════════════════════════════════
# DIAGNÓSTICO PASO A PASO
# ══════════════════════════════════════════
def main():
    print("\n" + "="*45)
    print("  DIAGNÓSTICO DFPLAYER MINI — SleepBear")
    print("="*45)

    # ── PASO 1: Inicializar UART ──────────────
    print("\n[1/6] Inicializando UART1...")
    print(f"      TX=GPIO{PIN_TX}  RX=GPIO{PIN_RX}  baud=9600")
    try:
        uart = UART(1, baudrate=9600, tx=PIN_TX, rx=PIN_RX)
        print("      ✓ UART inicializado correctamente")
        parpadear(1)
    except Exception as e:
        print(f"      ✗ FALLO al inicializar UART: {e}")
        print("      → Verifica que los pines TX/RX no estén en uso")
        return

    # ── PASO 2: Espera de arranque ────────────
    print("\n[2/6] Esperando arranque del DFPlayer (2s)...")
    print("      Si el LED del DFPlayer NO parpadeó al encender:")
    print("      → Verifica que VCC esté en 5V (pin VIN), NO en 3.3V")
    print("      → Verifica GND común con ESP32")
    time.sleep(2)
    parpadear(2)

    # ── PASO 3: Verificar si hay datos en el bus ──
    print("\n[3/6] Escuchando el bus UART por 1 segundo...")
    time.sleep_ms(100)
    datos = b""
    deadline = time.ticks_add(time.ticks_ms(), 1000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        if uart.any():
            datos += uart.read(uart.any())
        time.sleep_ms(10)

    if datos:
        print(f"      ✓ DFPlayer habló solo: {[hex(b) for b in datos]}")
        print("      → Comunicación UART funciona en RX")
    else:
        print("      ~ Sin datos espontáneos (normal en algunos módulos)")

    # ── PASO 4: Enviar consulta de estado ─────
    print("\n[4/6] Consultando estado del DFPlayer (cmd 0x42)...")
    enviar(uart, 0x42)  # Query status
    resp = leer_respuesta(uart, timeout_ms=800)
    if resp:
        print("      ✓ DFPlayer respondió — comunicación TX→RX OK")
    else:
        print("      ✗ Sin respuesta")
        print("      → Posibles causas:")
        print("         • Resistencia 1kΩ faltante en la línea TX→RX del DFPlayer")
        print("         • TX y RX cruzados al revés")
        print("         • DFPlayer sin alimentación 5V")

    # ── PASO 5: Ajustar volumen ───────────────
    print("\n[5/6] Enviando volumen = 20 (cmd 0x06)...")
    enviar(uart, 0x06, 20)
    leer_respuesta(uart, timeout_ms=500)
    time.sleep_ms(300)

    # ── PASO 6: Reproducir pista 1 ───────────
    print("\n[6/6] Intentando reproducir pista 1 (cmd 0x03)...")
    print("      Asegúrate de que la microSD tenga el archivo '0001.mp3'")
    enviar(uart, 0x03, 1)
    resp = leer_respuesta(uart, timeout_ms=1000)

    if resp:
        print("      ✓ DFPlayer procesó el comando")
        print("      Si no suena: revisa la bocina y el volumen de la microSD")
    else:
        print("      ✗ DFPlayer no respondió al comando de reproducción")

    # ── RESUMEN ───────────────────────────────
    print("\n" + "="*45)
    print("  RESUMEN DE DIAGNÓSTICO")
    print("="*45)
    print("""
  LED del DFPlayer al encender:
    Parpadea rápido → arrancó bien, problema en UART
    No parpadea     → sin 5V o módulo dañado

  Sin respuesta en paso 4 y 6:
    1. Conecta VCC a 5V (VIN del ESP32), no a 3.3V
    2. Agrega resistencia 1kΩ entre GPIO13 y RX del DFPlayer
    3. Verifica GND común
    4. Verifica que TX/RX no estén invertidos

  microSD:
    • Formato FAT32
    • Archivos: 0001.mp3, 0002.mp3 ...
    • Sin carpetas adicionales en la raíz
""")
    parpadear(5, ms=100)

main()