import cv2

for i in range(5):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        ret, frame = cap.read()
        print(f"Índice {i}: {'✓ captura imagen' if ret else '✗ abre pero no captura'}")
        cap.release()
    else:
        print(f"Índice {i}: no disponible")


cap = cv2.VideoCapture(2)  # el índice que encontraste
ret, frame = cap.read()
cv2.imwrite("prueba_cam.jpg", frame)  # guarda una foto para verificar
cap.release()
print("Foto guardada en prueba_cam.jpg")