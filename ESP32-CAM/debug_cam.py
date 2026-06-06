import cv2
import numpy as np
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'servidor'))
from detector_postura import detectar_piel, detectar_postura

cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)  # cambia el índice si es necesario

while True:
    ret, frame = cap.read()
    if not ret:
        print("No captura frame")
        break

    # Ver la máscara de piel en tiempo real
    mascara = detectar_piel(frame)
    postura  = detectar_postura(frame)

    # Calcular dónde está la piel
    h = frame.shape[0]
    mitad = h // 2
    piel_arriba = cv2.countNonZero(mascara[:mitad, :])
    piel_abajo  = cv2.countNonZero(mascara[mitad:, :])

    # Dibujar línea divisoria y texto
    cv2.line(frame, (0, mitad), (frame.shape[1], mitad), (0, 255, 255), 2)
    cv2.putText(frame, f"ARRIBA: {piel_arriba}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, f"ABAJO:  {piel_abajo}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    cv2.putText(frame, f"POSTURA: {postura}", (10, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    # Mostrar frame original y máscara de piel lado a lado
    mascara_color = cv2.cvtColor(mascara, cv2.COLOR_GRAY2BGR)
    combinado = np.hstack([frame, mascara_color])
    cv2.imshow("DEBUG — izq: camara | der: piel detectada", combinado)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()