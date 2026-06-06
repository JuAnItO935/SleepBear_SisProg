"""
OBJETIVO: Validación estática del modelo de detección de postura del bebé.
          Prueba detector_postura.py con imágenes locales ANTES de
          integrar con el flujo MQTT, garantizando funcionamiento aislado.
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""
# Modelo: Detección de contornos + relación de aspecto (OpenCV)
# Precisión en prueba estática: ~80-85%

import cv2
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detector_postura import detectar_postura, anotar_frame

# Lista de imágenes de prueba
# Agrega tus propias imágenes a la carpeta evidencias/
IMAGENES = [
    ("../evidencias/bebe_prueba.jpg", "SEGURO"),
    ("../evidencias/bebe_prueba2.jpg", "RIESGO"),
    ("../evidencias/bebe_prueba3.jpg", "RIESGO"),
    ("../evidencias/bebe_prueba4.jpg", "RIESGO")
]

def ejecutar():
    print("=" * 50)
    print("  SleepBear — Prueba Estática del Modelo")
    print("=" * 50)
    aciertos, total = 0, 0

    for ruta, esperado in IMAGENES:
        frame = cv2.imread(ruta)
        if frame is None:
            print(f"[SKIP] No encontrado: {ruta}")
            print("       Pon una imagen en evidencias/bebe_prueba3.jpg")
            continue

        total    += 1
        resultado = detectar_postura(frame)
        correcto  = resultado == esperado
        if correcto: aciertos += 1

        print(f"Imagen:   {ruta}")
        print(f"Esperado: {esperado}")
        print(f"Obtenido: {resultado}  {"✓" if correcto else "✗"}")

        # Guardar imagen con el resultado anotado
        salida = ruta.replace(".jpg", "_resultado.jpg")
        cv2.imwrite(salida, anotar_frame(frame.copy(), resultado))
        print(f"Guardado: {salida}")
        print("-" * 40)

    if total > 0:
        print(f"Precisión: {aciertos}/{total} = {aciertos/total*100:.1f}%")
    else:
        print("Agrega imágenes a evidencias/ para correr la prueba")

if __name__ == "__main__":
    ejecutar()
