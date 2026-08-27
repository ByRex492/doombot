//! Nucleo nativo de D.O.O.M.
//!
//! Aqui vive lo que corre en el camino caliente del audio: 20 veces por segundo
//! durante toda la sesion, y mas adelante 60 veces por segundo alimentando la
//! animacion del HUD. Es el unico sitio del proyecto donde el coste por llamada
//! de Python se paga tantas veces como para notarse.
//!
//! El resto sigue en Python a proposito. Reescribir aqui lo que no esta en ese
//! camino solo anadiria un paso de compilacion sin ganar nada.

use pyo3::prelude::*;

/// Nivel RMS de un bloque de muestras, de 0,0 a 1,0.
///
/// Es la medida que decide si hay voz o silencio, y la que hara respirar al
/// orbe de la interfaz. La raiz cuadratica media pondera la energia real de la
/// senal, a diferencia del pico, que se dispara con un solo chasquido.
#[pyfunction]
fn rms(muestras: Vec<f32>) -> f32 {
    if muestras.is_empty() {
        return 0.0;
    }
    let suma: f64 = muestras.iter().map(|x| (*x as f64) * (*x as f64)).sum();
    (suma / muestras.len() as f64).sqrt() as f32
}

/// Amplitud maxima absoluta del bloque.
///
/// Diagnostica el microfono mudo: un pico de 0,0 exacto significa que no llega
/// ni una muestra distinta de cero, que no es lo mismo que un microfono flojo.
#[pyfunction]
fn peak(muestras: Vec<f32>) -> f32 {
    muestras.iter().fold(0.0f32, |m, x| m.max(x.abs()))
}

/// RMS y pico en una sola pasada sobre las muestras.
///
/// La captura necesita las dos cifras de cada bloque. Calcularlas por separado
/// recorre el buffer dos veces y, sobre todo, cruza el puente Python-Rust dos
/// veces: ese cruce cuesta mas que la aritmetica.
#[pyfunction]
fn nivel(muestras: Vec<f32>) -> (f32, f32) {
    if muestras.is_empty() {
        return (0.0, 0.0);
    }
    let mut suma = 0.0f64;
    let mut maximo = 0.0f32;
    for x in &muestras {
        suma += (*x as f64) * (*x as f64);
        let a = x.abs();
        if a > maximo {
            maximo = a;
        }
    }
    ((suma / muestras.len() as f64).sqrt() as f32, maximo)
}

/// Suaviza el nivel con ataque rapido y caida lenta.
///
/// Sin esto el indicador parpadea en cada pausa entre silabas y parece roto. La
/// voz sube de golpe y baja despacio, asi que el filtro tiene que ser asimetrico:
/// un promedio simetrico se come los ataques y arrastra los finales.
///
/// `anterior` es el valor suavizado previo; `alfa_sube` y `alfa_baja` son las
/// constantes de cada direccion, de 0,0 a 1,0.
#[pyfunction]
#[pyo3(signature = (actual, anterior, alfa_sube=0.55, alfa_baja=0.12))]
fn suavizar(actual: f32, anterior: f32, alfa_sube: f32, alfa_baja: f32) -> f32 {
    let alfa = if actual > anterior { alfa_sube } else { alfa_baja };
    anterior + alfa * (actual - anterior)
}

#[pymodule]
fn doomkit(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(rms, m)?)?;
    m.add_function(wrap_pyfunction!(peak, m)?)?;
    m.add_function(wrap_pyfunction!(nivel, m)?)?;
    m.add_function(wrap_pyfunction!(suavizar, m)?)?;
    m.add_function(wrap_pyfunction!(similitudes, m)?)?;
    m.add("__doc__", "Nucleo nativo de D.O.O.M: medidas del camino caliente del audio.")?;
    Ok(())
}

/// Similitud coseno de una consulta contra un lote de vectores empaquetados.
///
/// Este SI es el camino caliente que justifica bajar a nativo. La memoria
/// compara la pregunta con cada recuerdo guardado, uno a uno, en Python puro:
/// medido, 81 ms por cada mil recuerdos, y crece de forma lineal. No se puede
/// vectorizar con numpy sin reestructurar el almacen, porque los vectores
/// llegan como BLOB de SQLite de uno en uno.
///
/// `corpus` son los vectores concatenados y `dim` la longitud de cada uno. Se
/// pasa todo de golpe para cruzar el puente Python-Rust una vez y no mil.
#[pyfunction]
fn similitudes(consulta: Vec<f32>, corpus: Vec<f32>, dim: usize) -> PyResult<Vec<f32>> {
    if dim == 0 || consulta.len() != dim {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "La consulta no mide 'dim' componentes.",
        ));
    }
    if corpus.len() % dim != 0 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "El corpus no es un multiplo exacto de 'dim'.",
        ));
    }

    let norma_q: f32 = consulta.iter().map(|x| x * x).sum::<f32>().sqrt();
    if norma_q == 0.0 {
        return Ok(vec![0.0; corpus.len() / dim]);
    }

    let mut salida = Vec::with_capacity(corpus.len() / dim);
    for trozo in corpus.chunks_exact(dim) {
        let mut punto = 0.0f32;
        let mut norma = 0.0f32;
        for (a, b) in consulta.iter().zip(trozo) {
            punto += a * b;
            norma += b * b;
        }
        let norma = norma.sqrt();
        salida.push(if norma == 0.0 { 0.0 } else { punto / (norma_q * norma) });
    }
    Ok(salida)
}
