# =============================================================================
# SCRIPT DE PRUEBA LOCAL — SLEEPBEAR (SIN MQTT / SIN IA)
# OBJETIVO: Verificar el estado físico de todos los sensores y actuadores
#           usando exclusivamente las funciones de tu capa HAL.
# =============================================================================

import time
from dispositivos import CajaDeSensores, CajaDeActuadores

print("=" * 60)
print("     INICIANDO TEST DE HARDWARE LOCAL — SLEEPBEAR 🐻")
print("=" * 60)

# 1. Inicializar los componentes a través de tu HAL
try:
    print("[SISTEMA] Inicializando dispositivos...")
    sensores = CajaDeSensores()
    actuadores = CajaDeActuadores()
    print("[SISTEMA] ✅ Inicialización exitosa.\n")
except Exception as e:
    print("[CRÍTICO] Falló la inicialización de la HAL:", e)
    import sys
    sys.exit()

# =============================================================================
# FASE 1: PROBAR TODOS LOS SENSORES
# =============================================================================
print("-" * 50)
print("FASE 1: LECTURA DE SENSORES (Monitoreo de 5 segundos)")
print("-" * 50)

for i in range(1, 6):
    print(f"\n--- Muestra {i} de 5 ---")
    
    # MLX90614
    temp_bebe = sensores.obtener_temperatura_bebe()
    print(f"🌡️  Temp Bebé (MLX90614):  {temp_bebe} °C (Fiebre: {sensores.hay_fiebre()})")
    
    # DHT11
    temp_cuarto = sensores.obtener_temperatura_cuarto()
    hum_cuarto = sensores.obtener_humedad_cuarto()
    print(f"🏠 Cuarto (DHT11):         {temp_cuarto} °C | Humedad: {hum_cuarto}%")
    
    # LDR
    print(f"☀️ Nivel Luz (LDR):        {sensores.obtener_nivel_luz()} (¿Está oscuro?: {sensores.esta_oscuro()})")
    
    # Micrófono KY-038
    print(f"🎙️  Sonido Analógico:       {sensores.obtener_nivel_sonido()}%")
    print(f"🎛️  Sonido Digital (DO):    {sensores.hay_sonido_digital()}")
    
    time.sleep(1)

# =============================================================================
# FASE 2: PROBAR ACTUADORES (Barrido secuencial)
# =============================================================================
print("\n" + "-" * 50)
print("FASE 2: PRUEBA DE ACTUADORES EN CADENA")
print("-" * 50)

# ── 2.1 LED RGB
print("\n🎨 Probando LED RGB...")
print("-> Encendiendo VERDE (Todo bien)")
actuadores.indicar_todo_bien()
time.sleep(2)

print("-> Encendiendo AMARILLO (Atención)")
actuadores.indicar_atencion()
time.sleep(2)

print("-> Encendiendo ROJO (Alerta)")
actuadores.indicar_alerta()
time.sleep(2)

# ── 2.2 Ventilador DC
print("\n⚡ Probando Ventilador DC...")
print("-> ¡VENTILADOR ENCENDIDO!")
actuadores.activar_ventilador()
time.sleep(3)
print("-> Ventilador Apagado.")
actuadores.desactivar_ventilador()
time.sleep(1)

# ── 2.3 DFPlayer Mini (Audio)
print("\n🎵 Probando Módulo de Audio DFPlayer Mini...")
print("-> Ajustando volumen a nivel 22...")
actuadores.ajustar_volumen(10)
time.sleep_ms(200) # Pausa técnica para la UART

print("-> Solicitando reproducir PISTA 1...")
actuadores.reproducir_musica_cuna(1)

print("🔊 Deberías escuchar música ahora. Esperando 7 segundos de reproducción...")
time.sleep(7)

print("-> Deteniendo música...")
actuadores.detener_musica()

# ── 2.4 Cierre Seguro
print("\n" + "=" * 60)
print("[SISTEMA] Pasando a estado seguro...")
actuadores.estado_seguro()
print("🎉 TEST FINALIZADO COMPLETAMENTE 🎉")
print("=" * 60)