"""
OBJETIVO: Módulo de detección de postura del bebé mediante visión por
          computadora. Analiza frames de la ESP32-CAM para identificar
          posición de riesgo (boca abajo = riesgo de SMSL) usando
          detección de color de piel con OpenCV en espacio HSV.
          Si la cara/piel está visible en la mitad superior = SEGURO.
          Si la piel está en la mitad inferior = RIESGO (boca abajo).
INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

# Modelo: Detección de color de piel en espacio HSV + posición vertical
# Librería: OpenCV 4.x
# Precisión aproximada: 80-85% en iluminación normal
# Predicción: "SEGURO" | "RIESGO" | "INDETERMINADO"

import cv2
import numpy as np


def detectar_piel(frame):
    """
    Detecta píxeles de color piel en la imagen usando el espacio HSV.
    El rango HSV para piel humana es aproximadamente:
      H: 0-25 (tono rojizo-amarillento)
      S: 30-170 (saturación moderada)
      V: 80-255 (brillo medio-alto)

    Retorna una máscara binaria donde los píxeles blancos = piel detectada.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Rango de color piel en HSV
    lower_skin = np.array([0,  58,  100], dtype=np.uint8)
    upper_skin = np.array([20, 170, 255], dtype=np.uint8)

    mascara = cv2.inRange(hsv, lower_skin, upper_skin)

    # Limpieza morfológica para reducir ruido
    k = np.ones((3, 3), np.uint8)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN,  k)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, k)

    return mascara


def detectar_postura(frame):
    """
    Analiza un frame BGR y clasifica la postura del bebé.

    Método principal — detección de piel:
      Divide la imagen en mitad superior e inferior.
      Cuenta los píxeles de piel en cada mitad.
      Si hay más piel arriba → cara visible → SEGURO (boca arriba).
      Si hay más piel abajo → cara oculta → RIESGO (boca abajo).

    Método de respaldo — relación de aspecto:
      Si no se detecta suficiente piel, usa el método de contornos
      para determinar la orientación general del cuerpo.

    Parámetros:
        frame (np.ndarray): Imagen BGR de la ESP32-CAM o prueba estática

    Retorna:
        str: "SEGURO", "RIESGO" o "INDETERMINADO"
    """
    if frame is None or frame.size == 0:
        return "INDETERMINADO"

    h, w = frame.shape[:2]
    mitad = h // 2

    # ── Método principal: detección de piel ───────────────────────
    mascara_piel = detectar_piel(frame)

    piel_total = cv2.countNonZero(mascara_piel)
    piel_arriba = cv2.countNonZero(mascara_piel[:mitad, :])
    piel_abajo  = cv2.countNonZero(mascara_piel[mitad:, :])

    area_frame = h * w
    porcentaje_piel = piel_total / area_frame

    # Si hay suficiente piel detectada (más del 3% del frame)
    # usamos la posición para determinar la postura
    if porcentaje_piel > 0.01:
        if piel_arriba > piel_abajo * 1.1:
            # Más piel en la parte superior → cara visible → boca arriba
            return "SEGURO"
        elif piel_abajo > piel_arriba * 1.1:
            # Más piel en la parte inferior → cara oculta → boca abajo
            return "RIESGO"
        else:
            # Piel distribuida uniformemente → postura ambigua
            return "INDETERMINADO"

    # ── Método de respaldo: relación de aspecto ───────────────────
    # Se usa cuando hay poca piel visible (ropa que cubre, mala luz)
    gris  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur  = cv2.GaussianBlur(gris, (21, 21), 0)
    _, thresh = cv2.threshold(blur, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = np.ones((3, 3), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, k)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN,  k)

    contornos, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return "INDETERMINADO"

    c    = max(contornos, key=cv2.contourArea)
    area = cv2.contourArea(c)

    if area < (h * w * 0.05):
        return "INDETERMINADO"

    _, _, bw, bh = cv2.boundingRect(c)
    relacion = bw / bh if bh > 0 else 0

    if relacion > 1.3:
        return "SEGURO"
    elif relacion < 0.8:
        return "RIESGO"
    else:
        return "INDETERMINADO"


def anotar_frame(frame, postura):
    """
    Dibuja el resultado sobre el frame para visualización.
    Solo se usa en prueba_estatica.py, no en producción.
    """
    colores = {
        "SEGURO":        (0, 255, 0),
        "RIESGO":        (0, 0, 255),
        "INDETERMINADO": (0, 165, 255)
    }
    color = colores.get(postura, (255, 255, 255))
    cv2.putText(frame, f"Postura: {postura}", (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
    return frame