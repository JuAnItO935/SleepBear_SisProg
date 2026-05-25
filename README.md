# SleepBear_SisProg

**Materia:** Sistemas Programables  
**Institución:** Instituto Tecnológico de León  
**Integrantes:**
- Aragón Guerrero Jacziry Berenice — 21240179
- Cortez Iñiguez Juan José — 21240173

---

## Descripción

SleepBear es un sistema embebido desarrollado sobre ESP32 en MicroPython que monitorea en tiempo real las condiciones de un bebé. Detecta temperatura corporal, temperatura y humedad del cuarto, nivel de luz y llanto, y responde de forma autónoma activando actuadores. Los datos se transmiten mediante MQTT y se persisten en Firebase Realtime Database.

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

## Protocolo MQTT

**Broker público:** `broker.hivemq.com:1883` (sin autenticación)

### Tópicos de sensores (ESP32 → broker)

| Tópico | Dirección | Dispositivo | Payload | Descripción |
|--------|-----------|-------------|---------|-------------|
| `sleepbear/sensores/temp_bebe` | PUBLICA | MLX90614 (GY-906) | `float °C` ej: `36.6` | Temperatura corporal del bebé por infrarrojo |
| `sleepbear/sensores/temp_cuarto` | PUBLICA | DHT11 | `float °C` ej: `24.0` | Temperatura ambiente del cuarto |
| `sleepbear/sensores/humedad` | PUBLICA | DHT11 | `int %` 0–100 | Humedad relativa del cuarto |
| `sleepbear/sensores/nivel_luz` | PUBLICA | LDR | `float %` 0.0–100.0 | Porcentaje de luminosidad del cuarto |
| `sleepbear/sensores/nivel_sonido` | PUBLICA | KY-038 (AO) | `float %` 0.0–100.0 | Nivel analógico de sonido ambiente |
| `sleepbear/sensores/llanto` | PUBLICA | KY-038 (AO+DO) | `bool` true/false | Resultado del filtro de mayoría (5 muestras) |
| `sleepbear/sensores/fiebre` | PUBLICA | MLX90614 | `bool` true/false | True si temp_bebe ≥ 38.0 °C |
| `sleepbear/sensores/modo_noche` | PUBLICA | LDR | `bool` true/false | True si nivel_luz < 20 % |

### Tópicos de actuadores (broker → ESP32)

| Tópico | Dirección | Dispositivo | Payload | Descripción |
|--------|-----------|-------------|---------|-------------|
| `sleepbear/actuadores/led` | SUSCRIBE | LED RGB | `"verde"` \| `"amarillo"` \| `"rojo"` \| `"azul"` \| `"apagado"` | Color del LED de estado |
| `sleepbear/actuadores/ventilador` | SUSCRIBE | Ventilador DC | `"on"` \| `"off"` | Encendido/apagado del ventilador |
| `sleepbear/actuadores/musica` | SUSCRIBE | DFPlayer Mini | `"play"` \| `"stop"` \| `"1"` \| `"2"`… | Control de reproducción de audio |
| `sleepbear/actuadores/volumen` | SUSCRIBE | DFPlayer Mini | `int` 0–30 | Nivel de volumen |

### Telemetría completa

| Tópico | Dirección | Payload | Descripción |
|--------|-----------|---------|-------------|
| `sleepbear/telemetria` | PUBLICA | JSON (10 claves) | Estado completo de `obtener_estado_completo()` con timestamp |
