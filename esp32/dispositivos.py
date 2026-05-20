# =============================================================================
# PROYECTO:     SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
# INTEGRANTES:  Jacziry Berenice Aragón Guerrero
#               Juan José Cortes Íñiguez
# DESCRIPCIÓN:  Biblioteca HAL (Hardware Abstraction Layer) que centraliza el
#               control de todos los periféricos del sistema SleepBear.
#               Gestiona la lectura de temperatura del bebé (MLX90614),
#               condiciones del cuarto (DHT11) y nivel de luz (LDR),
#               así como el control de música de cuna (DFPlayer Mini),
#               indicador LED RGB y ventilador automático DC.
# =============================================================================

from machine import Pin, I2C, ADC, PWM, UART
import dht
import time


# =============================================================================
# CLASE: CajaDeSensores
# Gestiona todos los sensores del sistema SleepBear.
# =============================================================================

class CajaDeSensores:

    # Dirección I2C del sensor MLX90614
    DIRECCION_MLX = 0x5A
    # Registro de temperatura del objeto (bebé)
    REG_TEMP_OBJETO = 0x07
    # Tamaño del buffer para promedios móviles
    TAMANO_BUFFER = 5

    def __init__(self, pin_dht=4, pin_ldr=34, pin_sda=21, pin_scl=22,
                 pin_microfono_do=35, pin_microfono_ao=36):
        # ── Sensor MLX90614: temperatura sin contacto del bebé (I2C)
        self._i2c = I2C(0, sda=Pin(pin_sda), scl=Pin(pin_scl), freq=100000)

        # ── Sensor DHT11: temperatura y humedad del cuarto
        self._dht11 = dht.DHT11(Pin(pin_dht))

        # ── Sensor LDR: nivel de luz del cuarto (entrada analógica)
        self._ldr = ADC(Pin(pin_ldr))
        self._ldr.atten(ADC.ATTN_11DB)  # Rango completo: 0 a 3.3V

        # ── Sensor KY-038: micrófono para detección de llanto del bebé      
        self._mic_digital  = Pin(pin_microfono_do, Pin.IN)	#    DO  → salida digital (umbral ajustable con potenciómetro en la placa)
        self._mic_analogico = ADC(Pin(pin_microfono_ao))	#    AO  → salida analógica (nivel continuo de sonido, 0–4095)
        self._mic_analogico.atten(ADC.ATTN_11DB)  # Rango completo: 0 a 3.3V

        # ── Buffers internos para promedios móviles
        self._buffer_temp_bebe   = []
        self._buffer_temp_cuarto = []
        self._buffer_luz         = []
        self._buffer_sonido		 = []

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODOS INTERNOS (auxiliares, no llamar desde main)
    # ─────────────────────────────────────────────────────────────────────────

    def _promedio_movil(self, buffer, valor_nuevo):
        # Parámetros: buffer (lista de lecturas anteriores), valor_nuevo (lectura actual)
        # Acción:     Agrega el nuevo valor al buffer y mantiene su tamaño máximo.
        #             Calcula el promedio para estabilizar lecturas con ruido.
        # Devuelve:   Promedio de los últimos valores en el buffer (float)
        buffer.append(valor_nuevo)
        if len(buffer) > self.TAMANO_BUFFER:
            buffer.pop(0)
        return round(sum(buffer) / len(buffer), 2)

    def _leer_registro_mlx(self, registro):
        # Parámetros: registro (dirección del registro I2C a leer)
        # Acción:     Lee 3 bytes del MLX90614 y convierte el valor crudo
        #             a grados Celsius usando la fórmula del fabricante.
        # Devuelve:   Temperatura en °C (float), o None si ocurre un error
        try:
            datos = self._i2c.readfrom_mem(self.DIRECCION_MLX, registro, 3)
            valor_crudo = (datos[1] << 8) | datos[0]
            temperatura = valor_crudo * 0.02 - 273.15
            return round(temperatura, 2)
        except Exception as error:
            print("[ERROR] Fallo en lectura MLX90614:", error)
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODOS PÚBLICOS: Lectura de sensores
    # ─────────────────────────────────────────────────────────────────────────

    def obtener_temperatura_bebe(self):
        # Parámetros: ninguno
        # Acción:     Lee la temperatura corporal del bebé con el sensor
        #             infrarrojo MLX90614 sin necesidad de tocarlo.
        #             Aplica promedio móvil para estabilizar la lectura.
        # Devuelve:   Temperatura del bebé en °C (float), o None si falla
        temp = self._leer_registro_mlx(self.REG_TEMP_OBJETO)
        if temp is not None:
            return self._promedio_movil(self._buffer_temp_bebe, temp)
        return None

    def obtener_temperatura_cuarto(self):
        # Parámetros: ninguno
        # Acción:     Lee la temperatura ambiente del cuarto usando el DHT11.
        #             Aplica promedio móvil para evitar lecturas inestables.
        # Devuelve:   Temperatura del cuarto en °C (float), o None si falla
        try:
            self._dht11.measure()
            temp = self._dht11.temperature()
            return self._promedio_movil(self._buffer_temp_cuarto, float(temp))
        except Exception as error:
            print("[ERROR] Fallo en lectura DHT11 (temperatura):", error)
            return None

    def obtener_humedad_cuarto(self):
        # Parámetros: ninguno
        # Acción:     Lee la humedad relativa del cuarto usando el DHT11.
        # Devuelve:   Humedad en porcentaje % (int), o None si falla
        try:
            self._dht11.measure()
            return self._dht11.humidity()
        except Exception as error:
            print("[ERROR] Fallo en lectura DHT11 (humedad):", error)
            return None

    def obtener_nivel_luz(self):
        # Parámetros: ninguno
        # Acción:     Lee el valor analógico del sensor LDR y lo convierte
        #             a un porcentaje de luminosidad de 0 (oscuro) a 100 (muy iluminado).
        #             Aplica promedio móvil para estabilizar la lectura.
        # Devuelve:   Nivel de luz de 0 a 100 (float)
        valor_crudo = self._ldr.read()
        porcentaje  = round((valor_crudo / 4095) * 100, 1)
        return self._promedio_movil(self._buffer_luz, porcentaje)

    def esta_oscuro(self, umbral=20):
        # Parámetros: umbral (porcentaje de luz por debajo del cual es de noche, default 20)
        # Acción:     Compara el nivel de luz actual con el umbral configurado.
        # Devuelve:   True si el cuarto está oscuro, False si hay luz suficiente
        return self.obtener_nivel_luz() < umbral

    def hay_fiebre(self, umbral=38.0):
        # Parámetros: umbral (temperatura en °C considerada como fiebre, default 38.0)
        # Acción:     Verifica si la temperatura del bebé supera el umbral de fiebre.
        # Devuelve:   True si se detecta fiebre, False si la temperatura es normal
        temp = self.obtener_temperatura_bebe()
        if temp is not None:
            return temp >= umbral
        return False

    def cuarto_muy_caliente(self, umbral=28.0):
        # Parámetros: umbral (temperatura en °C considerada peligrosa para el cuarto, default 28.0)
        # Acción:     Verifica si la temperatura del cuarto supera el umbral seguro.
        # Devuelve:   True si el cuarto está demasiado caliente, False si es adecuado
        temp = self.obtener_temperatura_cuarto()
        if temp is not None:
            return temp >= umbral
        return False

    def obtener_nivel_sonido(self):
        # Parámetros: ninguno
        # Acción:     Lee la salida analógica del KY-038 y la convierte a un
        #             porcentaje de 0 (silencio total) a 100 (volumen máximo).
        #             Aplica promedio móvil para suavizar picos de ruido aleatorio.
        # Devuelve:   Nivel de sonido de 0 a 100 (float)
        valor_crudo = self._mic_analogico.read()
        porcentaje  = round((valor_crudo / 4095) * 100, 1)
        return self._promedio_movil(self._buffer_sonido, porcentaje)
 
    def hay_sonido_digital(self):
        # Parámetros: ninguno
        # Acción:     Lee la salida digital DO del KY-038, cuyo umbral se regula
        #             físicamente con el potenciómetro de la placa del sensor.
        #             Devuelve True en cuanto el sonido supera ese umbral ajustado.
        # Devuelve:   True si el sonido supera el umbral configurado, False si no
        return self._mic_digital.value() == 1
 
    def detectar_llanto(self, umbral_pct=60, muestras=5, intervalo_ms=40):
        # Parámetros: umbral_pct   (% de volumen analógico para considerar llanto, default 60)
        #             muestras     (cuántas lecturas consecutivas deben superar el umbral, default 5)
        #             intervalo_ms (milisegundos entre cada muestra, default 40)
        # Acción:     Toma varias muestras en rápida sucesión para distinguir un llanto
        #             sostenido del ruido esporádico. Solo confirma llanto si la mayoría
        #             de muestras supera el umbral, evitando falsas alarmas por golpes
        #             o ruidos puntuales.
        # Devuelve:   True si se detecta llanto sostenido, False si es ruido pasajero
        detecciones = 0
        for _ in range(muestras):
            if self.obtener_nivel_sonido() >= umbral_pct:
                detecciones += 1
            time.sleep_ms(intervalo_ms)
        return detecciones >= (muestras // 2 + 1)    

    def obtener_estado_completo(self):
        # Parámetros: ninguno
        # Acción:     Consulta todos los sensores simultáneamente y construye
        #             un resumen completo del estado del entorno del bebé.
        # Devuelve:   Diccionario con todos los valores de los sensores y sus estados
        return {
            "temperatura_bebe":   self.obtener_temperatura_bebe(),
            "temperatura_cuarto": self.obtener_temperatura_cuarto(),
            "humedad_cuarto":     self.obtener_humedad_cuarto(),
            "nivel_luz":          self.obtener_nivel_luz(),
            "hay_fiebre":         self.hay_fiebre(),
            "cuarto_caliente":    self.cuarto_muy_caliente(),
            "esta_oscuro":        self.esta_oscuro(),
            "nivel_sonido":       self.obtener_nivel_sonido(),
            "sonido_digital":     self.hay_sonido_digital(),
            "llanto_detectado":   self.detectar_llanto(),
        }


# =============================================================================
# CLASE: CajaDeActuadores
# Gestiona todos los actuadores del sistema SleepBear.
# =============================================================================

class CajaDeActuadores:

    # Volumen inicial del DFPlayer Mini (rango: 0 a 30)
    VOLUMEN_INICIAL = 15

    def __init__(self, pin_led_r=25, pin_led_g=26, pin_led_b=27,
                 pin_ventilador=32, pin_uart_tx=13, pin_uart_rx=14):
        # ── LED RGB: indicador visual de estado (PWM para control de brillo)
        self._led_rojo  = PWM(Pin(pin_led_r), freq=1000)
        self._led_verde = PWM(Pin(pin_led_g), freq=1000)
        self._led_azul  = PWM(Pin(pin_led_b), freq=1000)

        # ── Ventilador DC 5V controlado mediante transistor NPN
        self._ventilador = Pin(pin_ventilador, Pin.OUT)
        self._ventilador.off()

        # ── DFPlayer Mini: módulo de audio para música de cuna (UART)
        self._uart = UART(1, baudrate=9600, tx=pin_uart_tx, rx=pin_uart_rx)
        time.sleep(1)  # Esperar a que el DFPlayer Mini arranque correctamente
        self._enviar_comando_dfplayer(0x06, self.VOLUMEN_INICIAL)

        # ── Estado interno del sistema
        self._ventilador_activo = False
        self._musica_activa     = False

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODOS INTERNOS (auxiliares, no llamar desde main)
    # ─────────────────────────────────────────────────────────────────────────

    def _enviar_comando_dfplayer(self, comando, parametro=0):
        # Parámetros: comando (byte de instrucción DFPlayer), parametro (valor del comando)
        # Acción:     Construye y envía el paquete de 10 bytes requerido por el
        #             protocolo del DFPlayer Mini a través del puerto UART.
        # Devuelve:   nada
        msb      = (parametro >> 8) & 0xFF
        lsb      = parametro & 0xFF
        suma     = 0xFF + 0x06 + comando + 0x00 + msb + lsb
        checksum = (-(suma)) & 0xFFFF
        paquete  = bytes([
            0x7E, 0xFF, 0x06, comando, 0x00,
            msb, lsb,
            (checksum >> 8) & 0xFF,
            checksum & 0xFF,
            0xEF
        ])
        self._uart.write(paquete)

    def _establecer_color_led(self, rojo, verde, azul):
        # Parámetros: rojo, verde, azul (intensidad de cada canal, rango 0-1023)
        # Acción:     Ajusta el ciclo de trabajo PWM de cada canal del LED RGB.
        # Devuelve:   nada
        self._led_rojo.duty(rojo)
        self._led_verde.duty(verde)
        self._led_azul.duty(azul)

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODOS PÚBLICOS: Control de actuadores
    # ─────────────────────────────────────────────────────────────────────────

    def indicar_todo_bien(self):
        # Parámetros: ninguno
        # Acción:     Enciende el LED RGB en color verde para indicar
        #             que el bebé está bien y no hay alertas activas.
        # Devuelve:   nada
        self._establecer_color_led(0, 800, 0)

    def indicar_atencion(self):
        # Parámetros: ninguno
        # Acción:     Enciende el LED RGB en color amarillo para indicar
        #             que hay una condición que los padres deben revisar.
        # Devuelve:   nada
        self._establecer_color_led(800, 400, 0)

    def indicar_alerta(self):
        # Parámetros: ninguno
        # Acción:     Enciende el LED RGB en color rojo para indicar
        #             una alerta crítica que requiere atención inmediata.
        # Devuelve:   nada
        self._establecer_color_led(1023, 0, 0)

    def reproducir_musica_cuna(self, numero_pista=1):
        # Parámetros: numero_pista (número de archivo MP3 en la MicroSD, default 1)
        # Acción:     Envía el comando de reproducción al DFPlayer Mini
        #             para reproducir la pista de música de cuna indicada.
        # Devuelve:   nada
        self._enviar_comando_dfplayer(0x03, numero_pista)
        self._musica_activa = True

    def detener_musica(self):
        # Parámetros: ninguno
        # Acción:     Envía el comando de pausa al DFPlayer Mini
        #             para detener la reproducción de música de cuna.
        # Devuelve:   nada
        self._enviar_comando_dfplayer(0x16)
        self._musica_activa = False

    def ajustar_volumen(self, nivel):
        # Parámetros: nivel (volumen deseado entre 0=silencio y 30=máximo)
        # Acción:     Limita el valor al rango permitido y envía el comando
        #             de ajuste de volumen al DFPlayer Mini.
        # Devuelve:   nada
        nivel = max(0, min(30, nivel))
        self._enviar_comando_dfplayer(0x06, nivel)

    def activar_ventilador(self):
        # Parámetros: ninguno
        # Acción:     Activa el pin de control del ventilador DC para
        #             comenzar a circular aire y reducir la temperatura del cuarto.
        # Devuelve:   nada
        self._ventilador.on()
        self._ventilador_activo = True

    def desactivar_ventilador(self):
        # Parámetros: ninguno
        # Acción:     Desactiva el pin de control del ventilador DC
        #             para detener la circulación de aire.
        # Devuelve:   nada
        self._ventilador.off()
        self._ventilador_activo = False

    def activar_alerta_fiebre(self):
        # Parámetros: ninguno
        # Acción:     Ejecuta la secuencia completa de alerta por fiebre:
        #             enciende el LED rojo, baja el volumen y reproduce
        #             música suave para no asustar al bebé.
        # Devuelve:   nada
        self.indicar_alerta()
        self.ajustar_volumen(10)
        self.reproducir_musica_cuna(1)

    def calmar_llanto(self):
        # Parámetros: ninguno
        # Acción:     Ejecuta la secuencia de respuesta al llanto del bebé:
        #             enciende el LED en azul suave y reproduce música de
        #             cuna a volumen moderado para intentar calmarlo.
        # Devuelve:   nada
        self._establecer_color_led(0, 0, 400)
        self.ajustar_volumen(18)
        self.reproducir_musica_cuna(1)

    def modo_nocturno(self):
        # Parámetros: ninguno
        # Acción:     Configura el sistema en modo nocturno: LED al mínimo
        #             y volumen bajo para no interferir con el sueño del bebé.
        # Devuelve:   nada
        self._establecer_color_led(0, 50, 0)
        self.ajustar_volumen(8)

    def estado_seguro(self):
        # Parámetros: ninguno
        # Acción:     Apaga y detiene TODOS los actuadores del sistema de forma
        #             segura. Debe llamarse al apagar el sistema, ante cualquier
        #             error crítico o al presionar interrupción del programa.
        # Devuelve:   nada
        self.detener_musica()
        self.desactivar_ventilador()
        self._establecer_color_led(0, 0, 0)
        self._musica_activa     = False
        self._ventilador_activo = False
        print("[SISTEMA] Estado seguro activado. Todos los actuadores apagados.")
