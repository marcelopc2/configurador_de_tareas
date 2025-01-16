import streamlit as st
import requests
from decouple import config
from unidecode import unidecode

# Canvas API configuration
BASE_URL = "https://canvas.uautonoma.cl/api/v1"
API_TOKEN = config("TOKEN")  # Reemplaza esto con config("TOKEN") si usas decouple
HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
}

def obtener_todos_los_datos(url):
    """
    Obtiene todos los datos de una API con paginación.
    """
    datos = []
    while url:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        datos.extend(response.json())
        # Verifica si hay más páginas
        url = response.links.get("next", {}).get("url")
    return datos

def obtener_subcuentas(account_id):
    """
    Obtiene todas las subcuentas de una cuenta principal.
    """
    url = f"{BASE_URL}/accounts/{account_id}/sub_accounts?per_page=100"
    return obtener_todos_los_datos(url)

def obtener_cursos(subaccount_id):
    """
    Obtiene todos los cursos de una subcuenta.
    """
    url = f"{BASE_URL}/accounts/{subaccount_id}/courses?per_page=100"
    return obtener_todos_los_datos(url)

def normalizar_texto(texto):
    """
    Elimina acentos y convierte el texto a minúsculas.
    """
    return unidecode(texto).lower()

def buscar_cursos_en_subcuentas(account_id, termino_busqueda, subcuentas_procesadas=None):
    """
    Busca cursos que contengan palabras clave en todas las subcuentas (incluidas subsubcuentas de forma recursiva).
    """
    if subcuentas_procesadas is None:
        subcuentas_procesadas = set()

    resultados = []
    termino_normalizado = normalizar_texto(termino_busqueda)
    palabras_clave = set(termino_normalizado.split())

    subcuentas = obtener_subcuentas(account_id)
    
    for subcuenta in subcuentas:
        if subcuenta["id"] not in subcuentas_procesadas:
            subcuentas_procesadas.add(subcuenta["id"])

            # Buscar cursos en la subcuenta actual
            cursos = obtener_cursos(subcuenta["id"])
            for curso in cursos:
                nombre_curso_normalizado = normalizar_texto(curso["name"])
                
                # Coincidencia basada en palabras clave
                if any(palabra in nombre_curso_normalizado for palabra in palabras_clave):
                    resultados.append({
                        "id": curso["id"],
                        "nombre": curso["name"],
                        "subcuenta": subcuenta["name"],
                    })

            # Buscar subsubcuentas recursivamente
            resultados += buscar_cursos_en_subcuentas(subcuenta["id"], termino_busqueda, subcuentas_procesadas)

    return resultados

# Interfaz con Streamlit
st.title("Buscador Flexible de Cursos en Subcuentas")

account_id = st.number_input("ID de la cuenta principal", min_value=1, step=1)
termino_busqueda = st.text_input("Palabra(s) clave para buscar cursos")

if st.button("Buscar"):
    try:
        if termino_busqueda.strip():
            resultados = buscar_cursos_en_subcuentas(account_id, termino_busqueda)
            if resultados:
                st.success(f"Se encontraron {len(resultados)} cursos:")
                for curso in resultados:
                    st.write(
                        f"**ID:** {curso['id']} | "
                        f"**Nombre:** {curso['nombre']} | "
                        f"**Subcuenta:** {curso['subcuenta']}"
                    )
            else:
                st.warning("No se encontraron cursos que coincidan con el término de búsqueda.")
        else:
            st.warning("Por favor, ingresa al menos una palabra clave para buscar.")
    except Exception as e:
        st.error(f"Error: {e}")
