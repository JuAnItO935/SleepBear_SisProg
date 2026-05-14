# =============================================================================
# PROYECTO:     SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
# INTEGRANTES:  Jacziry Berenice Aragón Guerrero
#               Juan José Cortes Íñiguez
# DESCRIPCIÓN:  Script principal de prueba de la biblioteca HAL del sistema
#               SleepBear. Demuestra el uso de CajaDeSensores y CajaDeActuadores
#               para monitorear al bebé en tiempo real y responder automáticamente
#               a condiciones de fiebre, temperatura del cuarto y nivel de luz,
#               sin utilizar ninguna función nativa de MicroPython directamente.
# =============================================================================

from dispositivos import CajaDeSensores, CajaDeActuadores
import time

# ── Configuración inicial del sistema ─────────────────────────────────────────
sensores   = CajaDeSensores()
actuadores = CajaDeActuadores()

print("=" * 45)
print("   SleepBear - Sistema de Monitoreo Activo")
print("=" * 45)

# ── Bucle principal de monitoreo ──────────────────────────────────────────────
try:
    while True:

        # 1. Obtener estado completo de todos los sensores de una sola llamada
        estado = sensores.obtener_estado_completo()

        # 2. Mostrar lecturas en consola para verificación
        print("\n[SENSORES]")
        print("  Temp. bebé:   ", estado["temperatura_bebe"],  "°C")
        print("  Temp. cuarto: ", estado["temperatura_cuarto"], "°C")
        print("  Humedad:      ", estado["humedad_cuarto"],     "%")
        print("  Nivel de luz: ", estado["nivel_luz"],          "%")

        # 3. Lógica de decisión por nivel de prioridad

        # Prioridad 1: Fiebre en el bebé (situación crítica)
        if estado["hay_fiebre"]:
            print("[ALERTA CRITICA] Fiebre detectada en el bebé!")
            actuadores.activar_alerta_fiebre()

        # Prioridad 2: Cuarto demasiado caliente
        elif estado["cuarto_caliente"]:
            print("[ATENCION] Cuarto muy caliente, activando ventilador...")
            actuadores.indicar_atencion()
            actuadores.activar_ventilador()

        # Prioridad 3: Todo en orden
        else:
            actuadores.desactivar_ventilador()
            actuadores.indicar_todo_bien()
            print("[OK] Todas las condiciones son normales.")

        # 4. Ajuste automático según nivel de luz (modo nocturno o diurno)
        if estado["esta_oscuro"]:
            print("[MODO] Noche detectada, ajustando a modo nocturno.")
            actuadores.modo_nocturno()
        else:
            actuadores.ajustar_volumen(15)

        # 5. Esperar antes de la siguiente lectura
        time.sleep(2)

except KeyboardInterrupt:
    # Al interrumpir el programa, activar estado seguro para apagar todo
    print("\n[SISTEMA] Apagado solicitado. Activando estado seguro...")
    actuadores.estado_seguro()
    print("[SISTEMA] SleepBear apagado correctamente.")
