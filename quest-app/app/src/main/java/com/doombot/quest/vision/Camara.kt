package com.doombot.quest.vision

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.params.OutputConfiguration
import android.hardware.camera2.params.SessionConfiguration
import android.media.Image
import android.media.ImageReader
import android.os.Handler
import android.os.HandlerThread
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeout

/**
 * Un fotograma de lo que ve el usuario: la Passthrough Camera API de Meta (Horizon OS v74+), que
 * es Camera2 de Android con dos metadatos propios (documentacion de Meta, 15/10/2026):
 *
 * - ``com.meta.extra_metadata.camera_source`` = 0: la camara RGB de passthrough;
 * - ``com.meta.extra_metadata.position``: 0 la izquierda, 1 la derecha (vista desde quien lleva
 *   las gafas). Se usa la izquierda.
 *
 * Bajo demanda, nunca continuo: se abre, se descartan los primeros fotogramas (la exposicion aun
 * se esta ajustando: el primero suele salir negro) y se cierra. Formato YUV420 -el interno de la
 * camara- a 1280x960, pasado a JPEG de como mucho 1024 px para mandarlo a un modelo con vision.
 */
class Camara(contexto: Context) {
  private val gestor = contexto.getSystemService(Context.CAMERA_SERVICE) as CameraManager

  /** El id de la camara de passthrough izquierda, o null si estas gafas no tienen (o no hay permiso). */
  fun buscar(): String? =
      runCatching {
            val pass =
                gestor.cameraIdList.filter { id ->
                  gestor.getCameraCharacteristics(id).get(FUENTE) == FUENTE_PASSTHROUGH
                }
            pass.firstOrNull { gestor.getCameraCharacteristics(it).get(POSICION) == 0 } ?: pass.firstOrNull()
          }
          .getOrNull()

  @SuppressLint("MissingPermission") // los permisos se piden antes (DoomActivity)
  suspend fun foto(maxLado: Int = 1024): ByteArray {
    val id = buscar() ?: throw IllegalStateException("estas gafas no tienen camara de passthrough accesible (Horizon OS v74+)")
    val hilo = HandlerThread("doom-camara").apply { start() }
    val manejador = Handler(hilo.looper)
    val lector = ImageReader.newInstance(ANCHO, ALTO, ImageFormat.YUV_420_888, 4)
    var camara: CameraDevice? = null
    var sesion: CameraCaptureSession? = null
    try {
      return withTimeout(8_000) {
        camara = abrir(id, manejador)
        sesion = configurar(camara!!, lector)
        val peticion = camara!!.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply { addTarget(lector.surface) }
        sesion!!.setRepeatingRequest(peticion.build(), null, manejador)
        val jpeg = fotograma(lector, manejador, descartar = 6)
        reducir(jpeg, maxLado)
      }
    } finally {
      runCatching { sesion?.close() }
      runCatching { camara?.close() }
      runCatching { lector.close() }
      hilo.quitSafely()
    }
  }

  private suspend fun abrir(id: String, manejador: Handler): CameraDevice =
      suspendCancellableCoroutine { cont ->
        @SuppressLint("MissingPermission")
        fun abrirYa() =
            gestor.openCamera(
                id,
                object : CameraDevice.StateCallback() {
                  override fun onOpened(c: CameraDevice) = cont.resume(c)

                  override fun onDisconnected(c: CameraDevice) {
                    c.close()
                    if (cont.isActive) cont.resumeWithException(IllegalStateException("camara desconectada"))
                  }

                  override fun onError(c: CameraDevice, error: Int) {
                    c.close()
                    if (cont.isActive) cont.resumeWithException(IllegalStateException("la camara no abre (error $error)"))
                  }
                },
                manejador)
        abrirYa()
      }

  private suspend fun configurar(camara: CameraDevice, lector: ImageReader): CameraCaptureSession =
      suspendCancellableCoroutine { cont ->
        val config =
            SessionConfiguration(
                SessionConfiguration.SESSION_REGULAR,
                listOf(OutputConfiguration(lector.surface)),
                Executors.newSingleThreadExecutor(),
                object : CameraCaptureSession.StateCallback() {
                  override fun onConfigured(s: CameraCaptureSession) = cont.resume(s)

                  override fun onConfigureFailed(s: CameraCaptureSession) {
                    if (cont.isActive) cont.resumeWithException(IllegalStateException("no se pudo configurar la camara"))
                  }
                })
        camara.createCaptureSession(config)
      }

  /** Espera ``descartar`` fotogramas y convierte el siguiente a JPEG. */
  private suspend fun fotograma(lector: ImageReader, manejador: Handler, descartar: Int): ByteArray =
      suspendCancellableCoroutine { cont ->
        var vistos = 0
        lector.setOnImageAvailableListener(
            { r ->
              val img = r.acquireLatestImage() ?: return@setOnImageAvailableListener
              try {
                vistos++
                if (vistos > descartar && cont.isActive) {
                  r.setOnImageAvailableListener(null, null)
                  cont.resume(aJpeg(img))
                }
              } finally {
                img.close()
              }
            },
            manejador)
      }

  companion object {
    private const val ANCHO = 1280
    private const val ALTO = 960
    private const val FUENTE_PASSTHROUGH = 0
    private val FUENTE = CameraCharacteristics.Key("com.meta.extra_metadata.camera_source", Int::class.java)
    private val POSICION = CameraCharacteristics.Key("com.meta.extra_metadata.position", Int::class.java)

    /** YUV_420_888 a NV21 (lo que entiende YuvImage), respetando el paso de fila y de pixel. */
    private fun aJpeg(img: Image): ByteArray {
      val w = img.width
      val h = img.height
      val nv21 = ByteArray(w * h * 3 / 2)
      val y = img.planes[0]
      var o = 0
      for (fila in 0 until h) {
        y.buffer.position(fila * y.rowStride)
        y.buffer.get(nv21, o, w)
        o += w
      }
      val u = img.planes[1]
      val v = img.planes[2]
      for (fila in 0 until h / 2) {
        for (col in 0 until w / 2) {
          val iv = fila * v.rowStride + col * v.pixelStride
          val iu = fila * u.rowStride + col * u.pixelStride
          nv21[o++] = v.buffer.get(iv)
          nv21[o++] = u.buffer.get(iu)
        }
      }
      val salida = ByteArrayOutputStream()
      YuvImage(nv21, ImageFormat.NV21, w, h, null).compressToJpeg(Rect(0, 0, w, h), 90, salida)
      return salida.toByteArray()
    }

    private fun reducir(jpeg: ByteArray, maxLado: Int): ByteArray {
      val bmp = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size) ?: return jpeg
      val escala = maxLado.toFloat() / maxOf(bmp.width, bmp.height)
      if (escala >= 1f) return jpeg
      val pequeno = Bitmap.createScaledBitmap(bmp, (bmp.width * escala).toInt(), (bmp.height * escala).toInt(), true)
      val salida = ByteArrayOutputStream()
      pequeno.compress(Bitmap.CompressFormat.JPEG, 82, salida)
      return salida.toByteArray()
    }
  }
}
