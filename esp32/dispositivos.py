# =============================================================================
# OBJETIVO: Gestión de Firebase y Dashboard de usuario.
#           Capa de abstracción de hardware (HAL) para SleepBear.
#           CajaDeSensores encapsula MLX90614, DHT11, LDR y KY-038.
#           CajaDeActuadores encapsula LED RGB, DFPlayer Mini y ventilador.
#           NUEVO: umbral adaptativo de llanto para evitar falsos positivos
#           por variaciones de ruido ambiente.
# INTEGRANTES: Aragón Guerrero Jacziry Berenice - 21240179
#              Cortez Iñiguez Juan José - 21240173
# PROYECTO: SleepBear - Sistema Inteligente de Monitoreo Nocturno para Bebés
# =============================================================================

import time
import dht
from machine import Pin, ADC, I2C, PWM, UART


class CajaDeSensores:

    DIRECCION_MLX   = 0x5A
    REG_TEMP_OBJETO = 0x07
    TAMANO_BUFFER   = 5

    # Umbral adaptativo de llanto
    MUESTRAS_CALIBRACION = 30
    FACTOR_LLANTO        = 1.3
    UMBRAL_MINIMO        = 25.0   # % absoluto mínimo para detectar llanto

    def __init__(self, pin_dht=4, pin_ldr=34, pin_sda=21, pin_scl=22,
                 pin_microfono_do=35, pin_microfono_ao=32):
        # NOTA: pin_microfono_ao cambiado a 36 (VP) — pin de solo-ADC,
        # no comparte función con ningún actuador.

        self._i2c           = I2C(0, sda=Pin(pin_sda), scl=Pin(pin_scl), freq=100000)
        self._dht11         = dht.DHT11(Pin(pin_dht))
        self._ldr           = Pin(pin_ldr, Pin.IN)
        self._mic_digital   = Pin(pin_microfono_do, Pin.IN)
        self._mic_analogico = ADC(Pin(pin_microfono_ao))
        self._mic_analogico.atten(ADC.ATTN_11DB)

        self._buffer_temp_bebe   = []
        self._buffer_temp_cuarto = []
        self._buffer_sonido      = []

        # FIX DHT11: caché compartida para temperatura y humedad.
        # Ambos métodos llaman a _medir_dht11() que solo ejecuta
        # measure() si han pasado ≥ 2 segundos desde la última lectura.
        self._dht_ultimo_tiempo = 0
        self._dht_temp_cache    = None
        self._dht_hum_cache     = None

        # Umbral adaptativo de llanto
        self._baseline_sonido    = None
        self._muestras_recogidas = 0
        self._acumulador_calibra = 0.0
        print("[HAL] Iniciando calibración de ruido ambiente...")

    # ── MÉTODOS INTERNOS ──────────────────────────────────────────────────────

    def _promedio_movil(self, buffer, valor_nuevo):
        buffer.append(valor_nuevo)
        if len(buffer) > self.TAMANO_BUFFER:
            buffer.pop(0)
        return round(sum(buffer) / len(buffer), 2)

    def _leer_registro_mlx(self, registro):
        try:
            datos       = self._i2c.readfrom_mem(self.DIRECCION_MLX, registro, 3)
            valor_crudo = (datos[1] << 8) | datos[0]
            return round(valor_crudo * 0.02 - 273.15, 2)
        except Exception as e:
            print("[ERROR] MLX90614:", e)
            return None

    def _medir_dht11(self):
        """
        FIX DHT11 HUMEDAD:
        Centraliza measure() con caché de 2 s para que temperatura y humedad
        no llamen al sensor dos veces en el mismo ciclo.
        El DHT11 no soporta más de 1 lectura por segundo; la segunda llamada
        lanzaba OSError y humedad siempre devolvía None.
        """
        ahora = time.ticks_ms()
        if time.ticks_diff(ahora, self._dht_ultimo_tiempo) >= 2000:
            try:
                self._dht11.measure()
                self._dht_temp_cache    = float(self._dht11.temperature())
                self._dht_hum_cache     = self._dht11.humidity()
                self._dht_ultimo_tiempo = ahora
            except Exception as e:
                print("[ERROR] DHT11 measure:", e)

    def _actualizar_baseline(self, nivel_sonido):
        if self._muestras_recogidas < self.MUESTRAS_CALIBRACION:
            self._acumulador_calibra += nivel_sonido
            self._muestras_recogidas += 1
            if self._muestras_recogidas == self.MUESTRAS_CALIBRACION:
                self._baseline_sonido = round(
                    self._acumulador_calibra / self.MUESTRAS_CALIBRACION, 2
                )
                print(f"[HAL] Calibración completa — baseline={self._baseline_sonido}%")
        else:
            alpha = 0.05
            self._baseline_sonido = round(
                alpha * nivel_sonido + (1 - alpha) * self._baseline_sonido, 2
            )

    # ── MÉTODOS PÚBLICOS: Lectura de sensores ─────────────────────────────────

    def obtener_temperatura_bebe(self):
        temp = self._leer_registro_mlx(self.REG_TEMP_OBJETO)
        if temp is not None:
            return self._promedio_movil(self._buffer_temp_bebe, temp)
        return None

    def obtener_temperatura_cuarto(self):
        """FIX DHT11: usa caché compartida, no llama measure() directamente."""
        self._medir_dht11()
        if self._dht_temp_cache is not None:
            return self._promedio_movil(self._buffer_temp_cuarto, self._dht_temp_cache)
        return None

    def obtener_humedad_cuarto(self):
        """FIX DHT11: usa caché compartida, retorna el valor guardado."""
        self._medir_dht11()
        return self._dht_hum_cache

    def obtener_nivel_luz(self):
        # FIX LDR: DO=0 significa que HAY luz (el módulo tiene resistencia
        # pull-up interna). Devolvemos el porcentaje de luminosidad de forma
        # intuitiva: 100 = cuarto iluminado, 0 = cuarto oscuro.
        return 100 if self._ldr.value() == 1 else 0

    def esta_oscuro(self):
        """FIX LDR: DO=1 → oscuro; DO=0 → hay luz. Corregido aquí."""
        return self._ldr.value() == 0

    def hay_fiebre(self, umbral=38.0):
        temp = self.obtener_temperatura_bebe()
        return temp is not None and temp >= umbral

    def cuarto_muy_caliente(self, umbral=28.0):
        temp = self.obtener_temperatura_cuarto()
        return temp is not None and temp >= umbral

    def obtener_nivel_sonido(self):
        """
        FIX MICRÓFONO:
        El ADC ahora usa pin 36 (VP) que es exclusivo de ADC.
        El pin 32 anterior era compartido con el ventilador,
        lo que hacía que todas las lecturas analógicas fueran 0
        después de inicializar el actuador.
        """
        valor_crudo = self._mic_analogico.read()
        porcentaje  = round((valor_crudo / 4095) * 100, 1)
        nivel       = self._promedio_movil(self._buffer_sonido, porcentaje)
        self._actualizar_baseline(nivel)
        return nivel

    def hay_sonido_digital(self):
        return self._mic_digital.value() == 1

    def detectar_llanto(self, muestras=100, intervalo_ms=5):
        """
        Detección de llanto por variación brusca del AO.
        El KY-038 tiene rango analógico pequeño (~1%) pero los cambios
        rápidos entre muestras consecutivas distinguen silencio de llanto.
        Silencio: ~26 cambios / 100 muestras
        Llanto:   ~84 cambios / 100 muestras
        Umbral:   50 cambios  (margen cómodo entre ambos)
        """
        UMBRAL_CAMBIOS = 65     # calibrado: silencio~26, ruido ambiente~50, llanto~84
        DIFF_MINIMA    = 5      # diferencia mínima entre lecturas para contar

        anterior = self._mic_analogico.read()
        cambios  = 0

        for _ in range(muestras):
            actual = self._mic_analogico.read()
            if abs(actual - anterior) > DIFF_MINIMA:
                cambios += 1
            anterior = actual
            time.sleep_ms(intervalo_ms)

        resultado = cambios >= UMBRAL_CAMBIOS
        print(f"[MIC] cambios={cambios}/{muestras} umbral={UMBRAL_CAMBIOS} llanto={resultado}")
        return resultado

    def obtener_estado_completo(self):
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
            "baseline_sonido":    self._baseline_sonido,
        }


# =============================================================================
# CLASE: CajaDeActuadores
# FIX PIN VENTILADOR: movido de pin 32 a pin 33 para liberar el ADC del
# micrófono. Pin 32 es ADC1_CH4; si se configura como Pin.OUT el ADC
# queda inoperante y el micrófono siempre lee 0.
# =============================================================================

class CajaDeActuadores:

    def __init__(self, pin_led_r=25, pin_led_g=26, pin_led_b=27,
                 pin_ventilador=33,           # FIX: era 32, ahora 33
                 pin_dfplayer_tx=18, pin_dfplayer_rx=19):

        self._led_rojo  = PWM(Pin(pin_led_r), freq=1000)
        self._led_verde = PWM(Pin(pin_led_g), freq=1000)
        self._led_azul  = PWM(Pin(pin_led_b), freq=1000)
        self._ventilador = Pin(pin_ventilador, Pin.OUT)
        self._ventilador.off()

        self._uart = UART(2, baudrate=9600,
                          tx=pin_dfplayer_tx, rx=pin_dfplayer_rx)

        self._musica_activa     = False
        self._ventilador_activo = False

        time.sleep_ms(500)
        self.ajustar_volumen(15)

    def _enviar_comando_dfplayer(self, comando, parametro=0):
        paquete = bytearray([
            0x7E, 0xFF, 0x06, comando, 0x00,
            (parametro >> 8) & 0xFF,
            parametro & 0xFF,
            0x00, 0x00, 0xEF
        ])
        suma = 0
        for b in paquete[1:7]:
            suma += b
        suma = (~suma + 1) & 0xFFFF
        paquete[7] = (suma >> 8) & 0xFF
        paquete[8] = suma & 0xFF
        self._uart.write(paquete)
        time.sleep_ms(30)

    def _establecer_color_led(self, rojo, verde, azul):
        self._led_rojo.duty(rojo)
        self._led_verde.duty(verde)
        self._led_azul.duty(azul)

    def indicar_todo_bien(self):
        self._establecer_color_led(0, 800, 0)

    def indicar_atencion(self):
        self._establecer_color_led(800, 400, 0)

    def indicar_alerta(self):
        self._establecer_color_led(1023, 0, 0)

    def reproducir_musica_cuna(self, numero_pista=1):
        if not self._musica_activa:
            self._enviar_comando_dfplayer(0x03, numero_pista)
            self._musica_activa = True

    def detener_musica(self):
        self._enviar_comando_dfplayer(0x16)
        self._musica_activa = False

    def ajustar_volumen(self, nivel):
        nivel = max(0, min(30, nivel))
        self._enviar_comando_dfplayer(0x06, nivel)

    def activar_ventilador(self):
        self._ventilador.on()
        self._ventilador_activo = True

    def desactivar_ventilador(self):
        self._ventilador.off()
        self._ventilador_activo = False

    def activar_alerta_fiebre(self):
        self.indicar_alerta()
        self.ajustar_volumen(10)
        self.reproducir_musica_cuna(1)

    def calmar_llanto(self):
        self._establecer_color_led(0, 0, 400)
        self.ajustar_volumen(18)
        if not self._musica_activa:
            self.reproducir_musica_cuna(1)

    def modo_nocturno(self):
        self._establecer_color_led(0, 50, 0)
        self.ajustar_volumen(8)

    def estado_seguro(self):
        self.detener_musica()
        self.desactivar_ventilador()
        self._establecer_color_led(0, 0, 0)
        self._musica_activa     = False
        self._ventilador_activo = False
        print("[HAL] Estado seguro — todos los actuadores apagados.")
