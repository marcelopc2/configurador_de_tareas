import streamlit as st
import requests
import pandas as pd
from decouple import config
import logging
import unicodedata
import re

# Configuración de logging (opcional, puedes ajustar el nivel)
logging.basicConfig(level=logging.INFO)
st.set_page_config(page_title="REVISADOR y CONFIGURADOR DE TAREAS ⛑️", page_icon="⛑️")

# Canvas API configuration
BASE_URL = "https://canvas.uautonoma.cl/api/v1"
API_TOKEN = config("TOKEN")
HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"   # Por defecto se usa JSON en otras llamadas
}

# Crear una sesión de requests para mejorar el rendimiento en múltiples llamadas
session = requests.Session()
session.headers.update(HEADERS)

def clean_string(input_string: str) -> str:
    cleaned = input_string.strip().lower()
    cleaned = unicodedata.normalize('NFD', cleaned)
    cleaned = re.sub(r'[^\w\s.,!?-]', '', cleaned)
    cleaned = re.sub(r'[\u0300-\u036f]', '', cleaned)
    return cleaned

def canvas_request(method, endpoint, payload=None):
    """
    Realiza peticiones a la API de Canvas de forma centralizada.
    
    :param method: Método HTTP ('get', 'post', 'put', 'delete')
    :param endpoint: Endpoint de la API (por ejemplo, "/courses/123/assignments")
    :param payload: Datos a enviar (para POST/PUT)
    :return: La respuesta en formato JSON o None en caso de error
    """
    url = f"{BASE_URL}{endpoint}"
    try:
        if method.lower() == "get":
            response = session.get(url)
        elif method.lower() == "post":
            response = session.post(url, json=payload)
        elif method.lower() == "put":
            response = session.put(url, json=payload)
        elif method.lower() == "delete":
            response = session.delete(url)
        else:
            st.error("Método HTTP no soportado")
            return None

        if not response.ok:
            st.error(f"Error en la petición a {url} ({response.status_code}): {response.text}")
            return None

        if response.text:
            return response.json()
        else:
            return None

    except requests.exceptions.RequestException as e:
        st.error(f"Excepción en la petición a {url}: {e}")
        return None

def parse_course_ids(input_text):
    """Limpia y procesa el input para extraer los course IDs."""
    cleaned = input_text.replace(",", "\n").replace(" ", "\n")
    return list(filter(None, map(lambda x: x.strip(), cleaned.split("\n"))))

def get_assignments(course_id):
    """Obtiene todas las tareas de un curso."""
    return canvas_request("get", f"/courses/{course_id}/assignments") or []

def check_group_categories(course_id):
    """Obtiene y verifica las categorías de grupo de un curso."""
    group_categories_response = canvas_request("get", f"/courses/{course_id}/group_categories")
    if group_categories_response is None:
        return None

    group_categories = group_categories_response

    trabajo_en_equipo = next((gc for gc in group_categories if gc.get("name") == "Equipo de trabajo"), None)
    project_groups = next((gc for gc in group_categories if gc.get("name") == "Project Groups"), None)

    return {
        "Equipo de trabajo": {
            "exists": trabajo_en_equipo is not None,
            "id": trabajo_en_equipo["id"] if trabajo_en_equipo else None,
        },
        "Project Groups": {
            "exists": project_groups is not None,
            "id": project_groups["id"] if project_groups else None,
        }
    }

def get_rubric_details(course_id, assignment):
    """Obtiene detalles de la rúbrica asociada a una tarea."""
    if assignment.get("rubric_settings"):
        rubric_used_for_grading = assignment.get("use_rubric_for_grading")
        rubric_settings = assignment["rubric_settings"]
        return {
            "has_rubric": True,
            "rubric_points": rubric_settings.get("points_possible"),
            "rubric_used_for_grading": rubric_used_for_grading,
            "name": rubric_settings.get("title")
        }
    return {"has_rubric": False, "rubric_points": None, "rubric_used_for_grading": False}

def get_module_name(course_id: str, assignment_group_id: str):
    """Obtiene el nombre, peso e id del módulo (assignment group) de la tarea."""
    response = canvas_request("get", f"/courses/{course_id}/assignment_groups/{assignment_group_id}")
    if response and isinstance(response, dict):
        return {
            "name": response.get("name"),
            "weight": response.get("group_weight"),
            "id": response.get("id")
        }
    else:
        return None

def distribuir_estudiantes(student_ids, min_size, max_size):
    """
    Distribuye los estudiantes en equipos cumpliendo con el tamaño mínimo y máximo.
    Se retorna una lista de listas, donde cada sublista representa un equipo.
    """
    teams = [student_ids[i:i + max_size] for i in range(0, len(student_ids), max_size)]
    
    # Ajustar equipos si el último tiene menos del tamaño mínimo
    while len(teams) > 1 and len(teams[-1]) < min_size:
        deficit = min_size - len(teams[-1])
        for i in range(deficit):
            extraido = False
            # Buscar en los equipos anteriores un estudiante que se pueda mover
            for j in range(len(teams) - 2, -1, -1):
                if len(teams[j]) > min_size:
                    teams[-1].append(teams[j].pop())
                    extraido = True
                    break
            if not extraido:
                break

    # Garantizar que ningún equipo tenga más de max_size estudiantes
    for i in range(len(teams)):
        while len(teams[i]) > max_size:
            if i + 1 < len(teams):
                teams[i+1].insert(0, teams[i].pop())
            else:
                teams.append([teams[i].pop()])

    return teams

def assign_students_to_teams(course_id, group_category_id, min_size=3, max_size=4):
    """
    Crea equipos en Canvas y asigna a cada estudiante a un equipo.
    Se utiliza la función 'distribuir_estudiantes' para dividir los IDs de los estudiantes.
    """
    students_response = canvas_request("get", f"/courses/{course_id}/students")
    if students_response is None:
        return

    student_ids = [student["id"] for student in students_response]
    
    teams = distribuir_estudiantes(student_ids, min_size, max_size)
    
    for idx, team in enumerate(teams):
        group_name = f"Equipo de trabajo {idx + 1}"
        create_payload = {"name": group_name}
        group_response = canvas_request("post", f"/group_categories/{group_category_id}/groups", create_payload)
        if group_response is None:
            continue

        group_id = group_response.get("id")
        st.info(f"Equipo '{group_name}' creado exitosamente con ID {group_id}.")
        for student_id in team:
            membership_payload = {"user_id": student_id}
            membership_response = canvas_request("post", f"/groups/{group_id}/memberships", membership_payload)
            if membership_response is None:
                st.error(f"Error al asignar al estudiante {student_id} al equipo '{group_name}'.")
            else:
                st.success(f"Estudiante {student_id} asignado al equipo '{group_name}'.")

    st.success("Todos los estudiantes han sido asignados a equipos exitosamente.")

def check_team_assignments(course_id):
    """
    Verifica si se han creado equipos y si todos los estudiantes están asignados a un equipo
    en la categoría 'Equipo de trabajo'.
    """
    group_categories = canvas_request("get", f"/courses/{course_id}/group_categories")
    if not group_categories:
        return None

    equipo_de_trabajo = next((gc for gc in group_categories if gc.get("name") == "Equipo de trabajo"), None)
    if not equipo_de_trabajo:
        return {"teams_created": False, "all_assigned": False}
    
    group_category_id = equipo_de_trabajo["id"]
    groups = canvas_request("get", f"/group_categories/{group_category_id}/groups")
    if not groups:
        return {"teams_created": False, "all_assigned": False}

    students_response = canvas_request("get", f"/courses/{course_id}/students")
    if not students_response:
        return None
    
    student_ids = {student["id"] for student in students_response}
    assigned_student_ids = set()

    for group in groups:
        memberships = canvas_request("get", f"/groups/{group['id']}/memberships")
        if memberships:
            assigned_student_ids.update(m.get("user_id") for m in memberships)

    all_assigned = student_ids.issubset(assigned_student_ids)
    return {
        "teams_created": True,
        "all_assigned": all_assigned,
        "unassigned_students": student_ids - assigned_student_ids,
        "total_students": student_ids
    }

def analyze_assignment_teamwork(course_id, assignment):
    """Analiza la tarea aplicando varios criterios y retorna los detalles."""
    rubric_details = get_rubric_details(course_id, assignment)
    group_categories_check = check_group_categories(course_id)
    module_info = get_module_name(course_id, assignment.get("assignment_group_id"))
    team_options = check_team_assignments(course_id)
    
    third_column = []
    third_column.append("✅" if rubric_details["has_rubric"] else "🟥")
    third_column.append("✅" if rubric_details["rubric_points"] == 100 else "🟥")
    third_column.append("✅" if rubric_details["rubric_used_for_grading"] else "🟥")
    third_column.append("✅" if assignment.get("submission_types") == ["online_upload"] else "🟥")
    third_column.append("✅" if assignment.get("allowed_attempts") == 2 else "🟥")
    third_column.append("✅" if assignment.get("grading_type") == "points" else "🟥")
    third_column.append("✅" if assignment.get("points_possible") == 100 else "🟥")
    third_column.append("✅" if int(module_info['weight']) == 30 else "🟥")
    third_column.append("✅" if clean_string(module_info["name"]) == clean_string(assignment.get("name")) else "🟥")
    third_column.append("✅" if assignment.get("group_category_id") else "🟥")
    third_column.append("✅" if group_categories_check["Equipo de trabajo"]["exists"] else "🟥")
    third_column.append("✅" if not group_categories_check["Project Groups"]["exists"] else "🟥")
    third_column.append("✅" if team_options != None  and team_options['teams_created'] else "🟥")
    third_column.append("✅" if team_options != None and team_options['all_assigned'] else "🟥")

    return {
        "Tiene rubrica": rubric_details["name"] if third_column[0] == "✅" else "NO TIENE (Requiere configuracion manual)",
        "Puntos rubrica": str(int(rubric_details["rubric_points"]) if rubric_details["has_rubric"] else "NO TIENE (Requiere configuracion manual)"),
        "Usa rubrica para calificar": "SI" if third_column[2] == "✅" else "NO",
        "Tipo de entrega": "En linea" if third_column[3] == "✅" else "Otro",
        "Intentos permitidos": str(assignment.get("allowed_attempts")),
        "Tipo de calificacion": "Puntos" if  third_column[5] == "✅" else "Otro",
        "Puntos posibles": str(int(assignment.get("points_possible"))),
        "Ponderacion": str(f"{int(module_info['weight'])}%"),
        "Modulo": str(module_info["name"]),
        "Es trabajo en grupo": "SI" if third_column[9] == "✅" else "NO",
        "Existe Equipo de trabajo": "SI" if third_column[10] == "✅" else "NO",
        "Existe Project Groups": "SI" if third_column[11] == "✅" else "NO",
        "Equipos creados": "SI" if third_column[12] == "✅" else "NO",
        "Alumnos Asignados": f"SI ({len(team_options['unassigned_students'])} sin asignar)" if third_column[13] == "✅" else "NO",
    }, third_column
    
def analyze_assignment_forum(course_id, assignment):
    """Analiza la tarea aplicando varios criterios y retorna los detalles."""
    rubric_details = get_rubric_details(course_id, assignment)
    module_info = get_module_name(course_id, assignment.get("assignment_group_id"))
    
    third_column = []
    third_column.append("✅" if rubric_details["has_rubric"] else "🟥")
    third_column.append("✅" if rubric_details["rubric_points"] == 100 else "🟥")
    third_column.append("✅" if rubric_details["rubric_used_for_grading"] else "🟥")
    third_column.append("✅" if assignment.get("submission_types") == ['discussion_topic'] else "🟥")
    third_column.append("✅" if assignment.get("allowed_attempts") == -1 else "🟥")
    third_column.append("✅" if assignment.get("grading_type") == "points" else "🟥")
    third_column.append("✅" if assignment.get("points_possible") == 100 else "🟥")
    third_column.append("✅" if int(module_info['weight']) == 20 else "🟥")
    third_column.append("✅" if clean_string(module_info["name"]) == clean_string(assignment.get("name")) else "🟥")
    third_column.append("✅" if assignment.get("discussion_type") == "threaded" else "🟥")

    return {
        "Tiene rubrica": rubric_details["name"] if third_column[0] == "✅" else "NO TIENE (Requiere configuracion manual)",
        "Puntos rubrica": str(int(rubric_details["rubric_points"]) if rubric_details["has_rubric"] else "NO TIENE (Requiere configuracion manual)"),
        "Usa rubrica para calificar": "SI" if third_column[2] == "✅" else "NO",
        "Tipo de entrega": "En linea" if third_column[3] == "✅" else "Otro",
        "Intentos permitidos": "Ilimitado" if assignment.get("allowed_attempts") == -1 else str(assignment.get("allowed_attempts")),
        "Tipo de calificacion": "Puntos" if  third_column[5] == "✅" else "Otro",
        "Puntos posibles": str(int(assignment.get("points_possible"))),
        "Ponderacion": str(f"{int(module_info['weight'])}%"),
        "Modulo": str(module_info["name"]),
        "Desactivar respuestas hilvadanas": "SI" if third_column[9] == "✅" else "NO"
    }, third_column
 
def analyze_assignment_finalwork(course_id, assignment):
    """Analiza la tarea aplicando varios criterios y retorna los detalles."""
    rubric_details = get_rubric_details(course_id, assignment)
    module_info = get_module_name(course_id, assignment.get("assignment_group_id"))
    
    third_column = []
    third_column.append("✅" if rubric_details["has_rubric"] else "🟥")
    third_column.append("✅" if rubric_details["rubric_points"] == 100 else "🟥")
    third_column.append("✅" if rubric_details["rubric_used_for_grading"] else "🟥")
    third_column.append("✅" if assignment.get("submission_types") == ["online_upload"] else "🟥")
    third_column.append("✅" if assignment.get("allowed_attempts") == 2 else "🟥")
    third_column.append("✅" if assignment.get("grading_type") == "points" else "🟥")
    third_column.append("✅" if assignment.get("points_possible") == 100 else "🟥")
    third_column.append("✅" if int(module_info['weight']) == 50 else "🟥")
    third_column.append("✅" if clean_string(module_info["name"]) == clean_string(assignment.get("name")) else "🟥")
    third_column.append("✅" if assignment.get("group_category_id") is None else "🟥")

    return {
        "Tiene rubrica": rubric_details["name"] if third_column[0] == "✅" else "NO TIENE (Requiere configuracion manual)",
        "Puntos rubrica": str(int(rubric_details["rubric_points"]) if rubric_details["has_rubric"] else "NO TIENE (Requiere configuracion manual)"),
        "Usa rubrica para calificar": "SI" if third_column[2] == "✅" else "NO",
        "Tipo de entrega": "En linea" if third_column[3] == "✅" else "Otro",
        "Intentos permitidos": str(assignment.get("allowed_attempts")),
        "Tipo de calificacion": "Puntos" if  third_column[5] == "✅" else "Otro",
        "Puntos posibles": str(int(assignment.get("points_possible"))),
        "Ponderacion": str(f"{int(module_info['weight'])}%"),
        "Modulo": str(module_info["name"]),
        "Es trabajo en grupo": "NO" if third_column[9] == "✅" else "SI",
    }, third_column
    
def display_details_as_table(details, estado):
    """Muestra los detalles en forma de tabla usando pandas."""
    data = {"Requerimiento": list(details.keys()), "Actual": list(details.values()), "Estado":estado}
    df = pd.DataFrame(data)
    st.table(df)

def flatten_assignment_payload(nested_payload):
    """
    Transforma un payload anidado en uno plano con claves que sigan el formato que espera Canvas.
    Por ejemplo, transforma:
       {"assignment": {"grading_type": "points", "submission_types": ["online_upload"], ...}}
    en:
       {"assignment[grading_type]": "points",
        "assignment[submission_types][]": "online_upload",
        "assignment[submission_type]": "online",
        ... }
    """
    assignment_data = nested_payload.get("assignment", {})
    flat = {}
    # Se asume que submission_types es una lista; se envía el primer valor
    if "submission_types" in assignment_data:
        flat["assignment[submission_types][]"] = assignment_data["submission_types"][0] if assignment_data["submission_types"] else ""
    # Se agrega un valor fijo para submission_type
    flat["assignment[submission_type]"] = "online"
    # Para el resto de claves
    for key, value in assignment_data.items():
        if key == "submission_types":
            continue  # ya se procesó
        flat[f"assignment[{key}]"] = value
    # Si no se especifica, se puede incluir group_assignment como true
    if "group_assignment" not in assignment_data:
        flat["assignment[group_assignment]"] = True
    return flat

def update_assignment(course_id, assignment_id, payload):
    """Actualiza la configuración de una tarea utilizando payload en formato form-encoded."""
    endpoint = f"/courses/{course_id}/assignments/{assignment_id}"
    url = f"{BASE_URL}{endpoint}"
    flat_payload = flatten_assignment_payload(payload)
    headers_form = HEADERS.copy()
    headers_form["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        response = session.put(url, data=flat_payload, headers=headers_form)
        if response.ok:
            st.success("Opciones del trabajo en grupo corregidos!")
            return response.json()
        else:
            st.error(f"Error al actualizar la tarea: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Excepción al actualizar la tarea: {e}")
        return None

def update_group(course_id: str, assignment_group_id: str, payload):
    """Actualiza la configuración de un grupo (módulo)."""
    response = canvas_request("put", f"/courses/{course_id}/assignment_groups/{assignment_group_id}", payload)
    if response:
        st.success("Opciones del grupo corregidas!")
        return True
    else:
        return False

def correct_teamwork_assignment(course_id):
    """
    Realiza las correcciones necesarias a la tarea 'Trabajo en equipo',
    actualizando la tarea, el módulo y la categoría de grupo según corresponda.
    """
    assignments = get_assignments(course_id)
    teamwork_assignments = [a for a in assignments if "trabajo en equipo" in a["name"].lower()]
    if not teamwork_assignments:
        st.info(f"No hay tareas 'Trabajo en equipo' en el curso {course_id}.")
        return

    # Se utiliza la primera tarea encontrada para corrección.
    teamwork_assignment = teamwork_assignments[0]
    correct_module = get_module_name(course_id, teamwork_assignment.get("assignment_group_id"))
    correct_group_categories = check_group_categories(course_id)
    correct_teams = check_team_assignments(course_id)
    
    payload_assignment = {}
    payload_modules = {}
    payload_group_categories = {}
    
    # Correcciones en la tarea
    if not teamwork_assignment.get("rubric_settings"):
        st.warning("Sin rúbrica asociada, la corrección debe ser realizada manualmente.")
    else:
        if teamwork_assignment["rubric_settings"].get("points_possible") != 100:
            st.warning(f"Esta rúbrica tiene el puntaje máximo mal configurado ({teamwork_assignment['rubric_settings']['points_possible']}).")
        if not teamwork_assignment.get("use_rubric_for_grading"):
            payload_assignment["use_rubric_for_grading"] = True
    
    if teamwork_assignment.get("grading_type") != "points":
        payload_assignment["grading_type"] = "points"
    
    if teamwork_assignment.get("submission_types") != ["online_upload"]:
        payload_assignment["submission_types"] = ["online_upload"]
    
    if teamwork_assignment.get("allowed_attempts") != 2:
        payload_assignment["allowed_attempts"] = 2

    if teamwork_assignment.get("points_possible") != 100:
        payload_assignment["points_possible"] = 100
    
    # Correcciones en el módulo (assignment group)
    if correct_module and correct_module.get("name") != teamwork_assignment.get("name"):
        payload_modules["name"] = teamwork_assignment.get("name")
        
    if correct_module and correct_module.get("weight") != 30:
        payload_modules["weight"] = 30

    # Correcciones en las categorías de grupo: eliminar 'Project Groups' si existe.
    if correct_group_categories and correct_group_categories["Project Groups"]["exists"]:
        response = canvas_request("delete", f"/group_categories/{correct_group_categories['Project Groups']['id']}")
        if response is not None:
            st.info("Eliminado 'Project Groups'.")
        else:
            st.error("Error al eliminar 'Project Groups'.")

    new_group_category_id = None      
    if not correct_group_categories or not correct_group_categories["Equipo de trabajo"]["exists"]:
        payload_group_categories["name"] = "Equipo de trabajo"
        payload_group_categories["self_signup"] = "disabled"
        payload_group_categories["auto_leader"] = "random"
        
        response = canvas_request("post", f"/courses/{course_id}/group_categories/", payload_group_categories)
        if response:
            new_group_category_id = response.get("id")
            payload_assignment["group_category_id"] = new_group_category_id
        else:
            st.warning("No se pudo crear la categoría 'Equipo de trabajo'.")
    else:
        payload_assignment["group_category_id"] = correct_group_categories["Equipo de trabajo"]["id"]
    
    # Si no se han creado equipos, asignar estudiantes a equipos.
    if correct_teams is None or not correct_teams.get("teams_created"):
        group_category_id = new_group_category_id if new_group_category_id else (correct_group_categories["Equipo de trabajo"]["id"] if correct_group_categories else None)
        if group_category_id:
            assign_students_to_teams(course_id, group_category_id, 3, 4)
        else:
            st.error("No se encontró o creó una categoría de grupo válida.")
    
    # Agregar configuración para Turnitin (revisión de similitud)
    payload_assignment["similarityDetectionTool"] = "Lti::MessageHandler_123"
    payload_assignment["configuration_tool_type"] = "Lti::MessageHandler"
    payload_assignment["report_visibility"] = "immediate"
    
    # Se prepara el payload final dentro de la clave "assignment"
    final_assignment_payload = {"assignment": payload_assignment}
    
    if payload_assignment:
        update_assignment(course_id, teamwork_assignment.get("id"), final_assignment_payload)
    if payload_modules and correct_module:
        update_group(course_id, correct_module["id"], payload_modules)

def main():
    st.title("REVISADOR y CONFIGURADOR DE TAREAS ⛑️")
    st.write("Ingresa uno o más IDs de curso:")

    input_ids = st.text_area("Course IDs", height=100)

    accion = st.radio("Seleccione una acción:", ("Revisar", "Corregir"))
    
    if st.button("Ejecutar"):
        st.divider()
        course_ids = parse_course_ids(input_ids)
        if not course_ids:
            st.warning("No hay IDs de curso válidos.")
        else:
            for course_id in course_ids:
                course_info = canvas_request('get', f"/courses/{course_id}")
                is_massive = False
                st.markdown(f"##### [{course_info.get('name')} - ({course_info.get('id')}) - {course_info.get('course_code')}](https://canvas.uautonoma.cl/courses/{course_id}/assignments)", unsafe_allow_html=True)
                if accion == "Revisar":
                    assignments = get_assignments(course_id)
                    forum_assignments = [a for a in assignments if "foro academico" in clean_string(a["name"].lower())]
                    teamwork_assignments = [a for a in assignments if "trabajo en equipo" in clean_string(a["name"].lower())]
                    final_assignments = [a for a in assignments if "trabajo final" in clean_string(a["name"].lower())]
                    #comprobando foro academico
                    if not forum_assignments:
                        st.info(f"No hay tareas llamadas 'Foro academico' en el curso {course_id}.")
                        # continue
                    else:
                        for assignment in forum_assignments:
                            st.write(f"##### Tarea: {assignment['name']}")
                            details, third_column = analyze_assignment_forum(course_id, assignment)
                            display_details_as_table(details, third_column)
                    #comprobando trabajo en equipo
                    if not teamwork_assignments:
                        st.info(f"No hay tareas llamadas 'Trabajo en equipo' en el curso {course_id}.")
                    else:
                        # continue
                        for assignment in teamwork_assignments:
                            st.write(f"##### Tarea: {assignment['name']}")
                            details, third_column = analyze_assignment_teamwork(course_id, assignment)
                            display_details_as_table(details, third_column)
                    #comprobando trabajo final
                    if not final_assignments:
                        st.info(f"No hay tareas llamadas 'Trabajo final' en el curso {course_id}.")
                    else:
                        # continue
                        for assignment in final_assignments:
                            st.markdown(f"##### Tarea: {assignment['name']}")
                            details, third_column = analyze_assignment_finalwork(course_id, assignment)
                            display_details_as_table(details, third_column)
                            st.divider()
                else:  # acción "Corregir"
                    correct_teamwork_assignment(course_id)

if __name__ == "__main__":
    main()
