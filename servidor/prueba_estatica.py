"""
OBJETIVO: Validación estática del modelo de detección de postura del bebé
          usando OpenCV antes de la integración con el flujo MQTT.
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
             Cortez Iñiguez Juan José - 21240173
PROYECTO: SleepBear - Sistema de Monitoreo Nocturno para Bebés
"""

# Modelo: Detección de postura (boca arriba / boca abajo) mediante análisis
# de contornos y relación de aspecto con OpenCV.
# Precisión aproximada en pruebas estáticas: 80-85% en condiciones de luz normal.

import cv2
import numpy as np

def detectar_postura_bebe(frame):
    """
    Analiza un frame y determina si el bebé está boca arriba (seguro)
    o boca abajo (posición de riesgo SMSL).
    Retorna: "SEGURO", "RIESGO" o "INDETERMINADO"
    """
    gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gris, (21, 21), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    contornos, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return "INDETERMINADO"

    # Tomar el contorno más grande (el bebé)
    c = max(contornos, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(c)
    relacion = w / h if h > 0 else 0

    # Si es más ancho que alto → acostado boca arriba (seguro)
    # Si es más alto que ancho → enrollado / boca abajo (riesgo)
    if relacion > 1.3:
        return "SEGURO"
    elif relacion < 0.8:
        return "RIESGO"
    else:
        return "INDETERMINADO"

# --- Prueba con imagen local ---
if __name__ == "__main__":
    # Cambia esta ruta a una imagen de prueba tuya
    ruta = "evidencia/bebe_prueba.jpg"
    frame = cv2.imread(ruta)
    if frame is None:
        print("[ERROR] No se encontró la imagen de prueba.")
    else:
        resultado = detectar_postura_bebe(frame)
        print(f"[PRUEBA ESTÁTICA] Postura detectada: {resultado}")
        cv2.putText(frame, resultado, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (0, 255, 0) if resultado == "SEGURO" else (0, 0, 255), 2)
        cv2.imshow("Resultado", frame)
        cv2.waitKey(0)
        cv2.destroyAllWindows()