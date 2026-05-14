# SleepBear_SisProg

# SleepBear — Pipeline de IA
## Arquitectura
ESP32-CAM → MQTT → servidor_ia.py (OpenCV) → MQTT → Actuadores ESP32

## Cómo ejecutar
1. Instalar dependencias: `pip install paho-mqtt opencv-python numpy`
2. Prueba estática: `python servidor/prueba_estatica.py`
3. Servidor IA: `python servidor/servidor_ia.py`
4. Flashear ESP32 con main.py y cam_publisher.py

## Modelo de IA
- Librería: OpenCV
- Técnica: Detección de contornos + relación de aspecto
- Predicción: Postura del bebé (SEGURO / RIESGO / INDETERMINADO)
- Precisión aproximada: 80-85%