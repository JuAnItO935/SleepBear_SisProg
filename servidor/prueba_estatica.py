"""
OBJETIVO: Validación estática del modelo de detección de postura del bebé.
          Prueba detector_postura.py con imágenes locales ANTES de integrar
          con el flujo MQTT, garantizando funcionamiento aislado.

CORRECCIÓN v2:
  • Permite elegir modo: "cenital", "frontal" o "auto"
  • Muestra ventana interactiva con el frame anotado (presiona cualquier
    tecla para pasar a la siguiente imagen, 'q' para salir)
  • Guarda el resultado anotado con el modo usado en el nombre del archivo
  • Calcula precisión por modo por separado

INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

import cv2
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detector_postura import detectar_postura, anotar_frame

# ── Configuración ──────────────────────────────────────────────────────────────
# Modo de detección: "cenital" | "frontal" | "auto"
# Para las pruebas estáticas con fotos desde arriba → "cenital"
# Para pruebas con la webcam frontal → "frontal" o "auto"
MODO = "auto"

# Lista de imágenes de prueba con resultado esperado
# Agrega tus propias imágenes a la carpeta evidencias/
IMAGENES = [
    ("../evidencias/bebe_prueba.jpg",  "SEGURO"),
    ("../evidencias/bebe_prueba2.jpg", "RIESGO"),
    ("../evidencias/bebe_prueba3.jpg", "RIESGO"),
    ("../evidencias/bebe_prueba4.jpg", "RIESGO"),
    ("../evidencias/prueba5.jpg", "SEGURO"),
    ("../evidencias/prueba6.jpg", "SEGURO"),
    ("../evidencias/prueba7.jpg", "RIESGO"),
    ("../evidencias/prueba8.jpg", "RIESGO"),
]

# Mostrar ventana con el frame anotado (requiere pantalla)
MOSTRAR_VENTANA = True

# Espera entre imágenes en ms (0 = espera tecla del usuario)
ESPERA_MS = 0


def ejecutar(modo=MODO):
    print("=" * 55)
    print("  SleepBear — Prueba Estática del Modelo")
    print(f"  Modo de detección: {modo.upper()}")
    print("=" * 55)

    aciertos = 0
    total    = 0
    errores  = []

    for ruta, esperado in IMAGENES:
        # Buscar imagen relativa al directorio del script
        ruta_abs = os.path.join(os.path.dirname(os.path.abspath(__file__)), ruta)
        frame = cv2.imread(ruta_abs)

        if frame is None:
            print(f"\n[SKIP] No encontrado: {ruta}")
            print(f"       Coloca la imagen en: {ruta_abs}")
            continue

        total    += 1
        resultado = detectar_postura(frame, modo=modo)
        correcto  = resultado == esperado

        if correcto:
            aciertos += 1
        else:
            errores.append((ruta, esperado, resultado))

        icono = "✓" if correcto else "✗"
        print(f"\nImagen  : {os.path.basename(ruta)}")
        print(f"Esperado: {esperado}")
        print(f"Obtenido: {resultado}  {icono}")

        # Guardar imagen anotada
        frame_vis = anotar_frame(frame.copy(), resultado, modo=modo)
        nombre_salida = ruta_abs.replace(".jpg", f"_resultado_{modo}.jpg")
        cv2.imwrite(nombre_salida, frame_vis)
        print(f"Guardado: {os.path.basename(nombre_salida)}")

        # Mostrar ventana si está habilitado
        if MOSTRAR_VENTANA:
            titulo = f"SleepBear Prueba [{os.path.basename(ruta)}] — {resultado}"
            cv2.imshow(titulo, frame_vis)
            tecla = cv2.waitKey(ESPERA_MS) & 0xFF
            cv2.destroyAllWindows()
            if tecla == ord('q'):
                print("\n[INFO] Salida anticipada por usuario.")
                break

        print("-" * 55)

    # ── Resumen final ──────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  RESUMEN")
    print("=" * 55)
    if total > 0:
        pct = aciertos / total * 100
        print(f"  Modo    : {modo.upper()}")
        print(f"  Aciertos: {aciertos}/{total} = {pct:.1f}%")
        if errores:
            print("\n  ERRORES:")
            for r, esp, obt in errores:
                print(f"    {os.path.basename(r)}: esperado={esp}, obtenido={obt}")
        if pct < 70:
            print("\n  ⚠ Precisión baja. Intenta cambiar MODO a 'cenital' o 'frontal'")
            print("    y ajusta _MIN_AREA_PIEL en detector_postura.py si el")
            print("    modo cenital no detecta bien la piel en tus imágenes.")
    else:
        print("  No se procesaron imágenes.")
        print("  Agrega imágenes a evidencias/ y actualiza la lista IMAGENES.")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    # Permite pasar el modo como argumento: python prueba_estatica.py cenital
    modo_arg = sys.argv[1] if len(sys.argv) > 1 else MODO
    if modo_arg not in ("cenital", "frontal", "auto"):
        print(f"[ERROR] Modo inválido: {modo_arg}")
        print("        Usa: cenital | frontal | auto")
        sys.exit(1)
    ejecutar(modo=modo_arg)

