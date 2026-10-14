plugins {
  alias(libs.plugins.android.application)
  alias(libs.plugins.jetbrains.kotlin.android)
  alias(libs.plugins.meta.spatial.plugin)
  alias(libs.plugins.jetbrains.kotlin.plugin.compose)
}

android {
  namespace = "com.doombot.quest"
  compileSdk = 34

  defaultConfig {
    applicationId = "com.doombot.quest"
    // Horizon OS es Android 14 (API 34): lo exige la documentacion de Meta.
    minSdk = 34
    targetSdk = 34
    versionCode = 2
    versionName = "0.2"
    // Las Quest 3/3S son arm64: sin las demas arquitecturas, onnxruntime pesa una cuarta parte.
    ndk { abiFilters += "arm64-v8a" }
  }

  packaging { resources.excludes.add("META-INF/LICENSE") }
  lint {
    abortOnError = false
    checkReleaseBuilds = false
  }
  buildTypes {
    release {
      // Release para instalar en las propias gafas: no depurable, asi Compose y el orbe van fluidos
      // (en debug, ART no optimiza y se nota a 72-90 Hz). Firmada con la clave de depuracion local:
      // no es para la tienda. Sin R8: el Spatial SDK usa reflexion y no hay reglas probadas.
      isMinifyEnabled = false
      signingConfig = signingConfigs.getByName("debug")
      proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
    }
  }
  buildFeatures {
    buildConfig = true
    compose = true
  }
  compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
  }
}

kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }

dependencies {
  // Meta Spatial SDK, bajo la Meta Platforms Technologies SDK License Agreement:
  // https://developers.meta.com/horizon/licenses/oculussdk/
  implementation(libs.meta.spatial.sdk.base)
  implementation(libs.meta.spatial.sdk.toolkit)
  implementation(libs.meta.spatial.sdk.vr)
  implementation(libs.meta.spatial.sdk.isdk)
  implementation(libs.meta.spatial.sdk.compose)

  implementation(libs.androidx.core.ktx)
  implementation(libs.androidx.lifecycle.runtime.ktx)
  implementation(libs.androidx.activity.compose)
  implementation(platform(libs.androidx.compose.bom))
  implementation(libs.androidx.ui)
  implementation(libs.androidx.ui.graphics)
  implementation(libs.androidx.material3)
  implementation(libs.kotlinx.coroutines)
  implementation(libs.androidx.datastore)
  // Servidor de ajustes en la red local (unos 100 KB) y el QR para abrirlo desde el movil.
  implementation(libs.nanohttpd)
  implementation(libs.zxing.core)
  implementation(libs.onnxruntime.android)

  testImplementation(libs.junit)
}

spatial {
  // El usuario no comparte datos de uso con Meta (lo eligio en su cuenta de desarrollador).
  allowUsageDataCollection.set(false)
}

// Ninguna clave en el codigo: si algo tiene forma de clave de un proveedor, no se compila.
// Las claves viven cifradas en las gafas (Almacen.kt) y llegan desde el movil (Ajustes).
val comprobarClaves by tasks.registering {
  val fuentes = fileTree("src") { include("**/*.kt", "**/*.xml", "**/*.html", "**/*.json", "**/*.properties") }
  inputs.files(fuentes)
  doLast {
    val forma = Regex("""(gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}|sk-[A-Za-z0-9_\-]{20,}|nvapi-[A-Za-z0-9_\-]{20,})""")
    val culpables = fuentes.files.filter { forma.containsMatchIn(it.readText()) }
    if (culpables.isNotEmpty()) {
      throw GradleException("Hay algo con forma de clave en: " + culpables.joinToString { it.name })
    }
  }
}
tasks.named("preBuild") { dependsOn(comprobarClaves) }
