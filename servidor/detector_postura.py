"""
OBJETIVO: Módulo de detección de postura del bebé mediante visión por
          computadora. Analiza frames para identificar posición de riesgo
          (boca abajo = riesgo de SMSL).

CORRECCIÓN v2 — DOBLE MODO:
  • MODO CENITAL  (vista desde arriba / pruebas estáticas con fotos):
    Usa segmentación de color de piel en HSV para ubicar la cabeza.
    Si la zona de piel más grande está en la MITAD SUPERIOR → SEGURO.
    Si está en la MITAD INFERIOR o no hay piel → RIESGO.
    Detecta automáticamente si no hay cara visible (imagen cenital pura).

  • MODO FRONTAL  (webcam en tiempo real):
    Usa Haar Cascades para detectar cara directamente.
    Si hay cara válida → SEGURO.
    Si no hay cara → RIESGO.

  La función detectar_postura() elige el modo automáticamente según la
  proporción de la imagen y la cantidad de piel detectada.
  También se puede forzar el modo con el parámetro `modo`.

INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
"""

import cv2
import numpy as np
import os

# ── Parámetros de detección Haar ──────────────────────────────────────────────
_MIN_VAR_CARA  = 150    # varianza mínima del ROI para cara real
_MIN_CARA_FRAC = 0.08   # tamaño mínimo de cara como fracción del frame

# ── Parámetros de segmentación de piel (modo cenital) ────────────────────────
# Rango HSV para piel humana (funciona bien bajo luz cálida e IR)
_PIEL_HSV_MIN = np.array([0,  20,  70],  dtype=np.uint8)
_PIEL_HSV_MAX = np.array([25, 255, 255], dtype=np.uint8)
_MIN_AREA_PIEL = 500    # píxeles mínimos para considerar zona de piel válida

# ── Cargar clasificadores Haar ─────────────────────────────────────────────────
def _cargar(nombre):
    rutas = [
        os.path.join(os.path.dirname(__file__), nombre),
        cv2.data.haarcascades + nombre,
    ]
    for ruta in rutas:
        if os.path.exists(ruta):
            clf = cv2.CascadeClassifier(ruta)
            if not clf.empty():
                return clf
    return None

_haar_frontal = _cargar("haarcascade_frontalface_default.xml")
_haar_perfil  = _cargar("haarcascade_profileface.xml")

if _haar_frontal:
    print("[IA] Haar frontal cargado")
if _haar_perfil:
    print("[IA] Haar perfil cargado")
if not _haar_frontal and not _haar_perfil:
    print("[IA] ADVERTENCIA: no se encontró ningún clasificador Haar")
    print("[IA] Solo modo cenital disponible")


# =============================================================================
# MODO CENITAL — segmentación de color de piel
# =============================================================================

def _detectar_postura_cenital(frame):
    """
    Modo cenital (vista desde arriba):
    Segmenta el color de piel en HSV y analiza en qué mitad del frame
    se concentra la mayor área de piel.

    Lógica:
      • La cabeza del bebé es la parte más redondeada y más clara
      • En vista cenital SEGURO (boca arriba): la cabeza está en la
        mitad superior del frame (la cámara ve la frente)
      • En vista cenital RIESGO (boca abajo): la nuca o la espalda
        ocupan el centro; hay poca piel visible y de menor área

    Retorna: "SEGURO", "RIESGO" o "INDETERMINADO"
    """
    h, w = frame.shape[:2]

    # Convertir a HSV para segmentación de piel
    hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, _PIEL_HSV_MIN, _PIEL_HSV_MAX)

    # Morfología para eliminar ruido pequeño
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask   = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)
    mask   = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # Encontrar contornos de zonas de piel
    contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contornos:
        return "RIESGO"  # sin piel visible → bebé cubierto / boca abajo

    # Encontrar el contorno más grande (zona de piel principal)
    mayor = max(contornos, key=cv2.contourArea)
    area  = cv2.contourArea(mayor)

    if area < _MIN_AREA_PIEL:
        return "RIESGO"  # área demasiado pequeña

    # Centroide de la zona de piel principal
    M = cv2.moments(mayor)
    if M["m00"] == 0:
        return "INDETERMINADO"
    cy = int(M["m01"] / M["m00"])  # coordenada Y del centroide

    # Si el centroide está en la mitad superior → cara mirando arriba = SEGURO
    # Si está en la mitad inferior → espalda o nuca = RIESGO
    mitad = h // 2
    if cy < mitad:
        return "SEGURO"
    else:
        return "RIESGO"


# =============================================================================
# MODO FRONTAL — Haar Cascades
# =============================================================================

def _cara_valida_en(imagen_gris, imagen_gris_orig, h, w, clf, es_flip):
    """
    Corre el clasificador sobre imagen_gris.
    Devuelve True si encuentra al menos una cara que pase los filtros
    de tamaño y varianza.
    """
    if clf is None:
        return False

    min_px = int(min(h, w) * _MIN_CARA_FRAC)
    caras  = clf.detectMultiScale(
        imagen_gris,
        scaleFactor=1.05,
        minNeighbors=4,
        minSize=(min_px, min_px),
        flags=cv2.CASCADE_SCALE_IMAGE
    )

    for (x, y, cw, ch) in caras:
        if cw > w * 0.6 or ch > h * 0.6:
            continue
        rx = (w - x - cw) if es_flip else x
        rx = max(0, min(rx, w - 1))
        ry = max(0, min(y, h - 1))
        roi = imagen_gris_orig[ry:ry+ch, rx:rx+cw]
        if roi.size == 0:
            continue
        if np.var(roi) >= _MIN_VAR_CARA:
            return True

    return False


def _detectar_postura_frontal(frame):
    """
    Modo frontal (webcam en tiempo real):
    Usa Haar Cascades para detectar la cara del bebé.
    Si hay cara válida → SEGURO, si no → RIESGO.
    """
    h, w = frame.shape[:2]
    gris     = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gris_eq  = cv2.equalizeHist(gris)
    gris_flp = cv2.flip(gris_eq, 1)

    for clf in [_haar_frontal, _haar_perfil]:
        for img, es_flip in [(gris_eq, False), (gris_flp, True)]:
            if _cara_valida_en(img, gris, h, w, clf, es_flip):
                return "SEGURO"

    return "RIESGO"


# =============================================================================
# FUNCIÓN PRINCIPAL — elige modo automáticamente
# =============================================================================

def detectar_postura(frame, modo="auto"):
    """
    Analiza un frame BGR y clasifica la postura del bebé.

    Parámetros:
        frame : imagen BGR (numpy array)
        modo  : "auto"    — elige según el frame (recomendado)
                "cenital" — fuerza modo vista desde arriba (pruebas estáticas)
                "frontal" — fuerza modo Haar Cascade (webcam en tiempo real)

    Retorna: "SEGURO", "RIESGO" o "INDETERMINADO"

    Modo AUTO:
        Si el frame tiene más píxeles de piel en proporción que lo esperado
        en una vista frontal normal, o si los Haar Cascades no detectan cara,
        activa el modo cenital como refuerzo.
        En la práctica: si Haar falla (típico en vistas de arriba), se cae al
        modo cenital automáticamente.
    """
    if frame is None or frame.size == 0:
        return "INDETERMINADO"

    if modo == "cenital":
        return _detectar_postura_cenital(frame)

    if modo == "frontal":
        return _detectar_postura_frontal(frame)

    # ── MODO AUTO ─────────────────────────────────────────────────────────────
    # 1. Intentar detección frontal (Haar)
    resultado_frontal = _detectar_postura_frontal(frame)

    if resultado_frontal == "SEGURO":
        # Haar encontró cara: definitivamente SEGURO
        return "SEGURO"

    # 2. Haar no encontró cara → puede ser vista cenital o bebé boca abajo
    #    Aplicar detección cenital como segunda opinión
    resultado_cenital = _detectar_postura_cenital(frame)

    if resultado_cenital == "SEGURO":
        # Cenital dice que la piel está en la mitad superior → SEGURO
        return "SEGURO"

    # Ambos métodos dicen RIESGO → alta confianza de que el bebé está boca abajo
    return "RIESGO"


# =============================================================================
# FUNCIÓN DE ANOTACIÓN
# =============================================================================

def anotar_frame(frame, postura, modo="auto"):
    """
    Dibuja el resultado sobre el frame para visualización en pruebas.
    En modo cenital también dibuja la máscara de piel y el centroide.
    """
    if frame is None:
        return frame

    colores = {
        "SEGURO":        (0, 255, 0),
        "RIESGO":        (0, 0, 255),
        "INDETERMINADO": (0, 165, 255)
    }
    color = colores.get(postura, (255, 255, 255))

    cv2.putText(frame, f"Postura: {postura}", (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
    cv2.putText(frame, f"Modo: {modo}", (10, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)

    h, w = frame.shape[:2]

    # ── Modo cenital: dibujar zona de piel ───────────────────────────────────
    if modo in ("cenital", "auto"):
        hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, _PIEL_HSV_MIN, _PIEL_HSV_MAX)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask   = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)
        mask   = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contornos:
            if cv2.contourArea(cnt) > _MIN_AREA_PIEL:
                cv2.drawContours(frame, [cnt], -1, (255, 150, 0), 2)

        # Línea de mitad del frame
        cv2.line(frame, (0, h//2), (w, h//2), (100, 100, 255), 1)
        cv2.putText(frame, "mitad", (5, h//2 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 255), 1)

    # ── Modo frontal: dibujar cajas de caras ─────────────────────────────────
    if modo in ("frontal", "auto"):
        gris    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gris_eq = cv2.equalizeHist(gris)
        for clf in [_haar_frontal, _haar_perfil]:
            if clf is None:
                continue
            min_px = int(min(h, w) * _MIN_CARA_FRAC)
            caras  = clf.detectMultiScale(gris_eq, 1.05, 4,
                                          minSize=(min_px, min_px))
            for (x, y, cw, ch) in caras:
                if cw < w * 0.6:
                    roi = gris[y:y+ch, x:x+cw]
                    var = np.var(roi) if roi.size > 0 else 0
                    c   = color if var >= _MIN_VAR_CARA else (100, 100, 100)
                    cv2.rectangle(frame, (x, y), (x+cw, y+ch), c, 2)

    return frame

