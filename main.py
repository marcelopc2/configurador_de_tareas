import streamlit as st
import pandas as pd
import requests
import random
from decouple import config
from functions import get_course_information, get_students, get_assignments, put_assignment, create_group_category, create_group_in_category, distribute_students_min3_max4_special, get_group_categories, delete_group_category, find_group_category, get_rubric_info, modify_module_name, get_module_name

BASE_URL = config('BASE_URL', default='https://canvas.uautonoma.cl/api/v1')
TOKEN = config('TOKEN')

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

def add_student_to_group(group_id: int, student_id: int, is_leader=False):
    local_headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"{BASE_URL}/groups/{group_id}/memberships"
    data = {
        "user_id": student_id
    }

    resp = requests.post(url, headers=local_headers, json=data)
    resp.raise_for_status()


def main():
    st.title("Configurador de tareas en UA Canvas".upper())

    # Campo para ingresar IDs de curso
    st.subheader("Ingresa los IDs de los cursos a verificar:")
    cursos_input = st.text_area("Ejemplo: 12345, 67890, 112233")

    # Botón para verificar
    if st.button("Buscar información"):
        if not cursos_input.strip():
            st.warning("No se ingresaron IDs de curso.")
            return

        cleaned_input = cursos_input.replace("\n", ",").replace("\r", ",")
        course_ids = cleaned_input.replace(",", " ").split()
        course_ids = [cid.strip() for cid in course_ids if cid.strip().isdigit()]

        if not course_ids:
            st.warning("No se encontraron IDs válidos.")
            return

        # Verificar Tareas
        for course_id in course_ids:
            try:
                # Info de curso
                course_info = get_course_information(course_id, BASE_URL, headers)
                course_name = course_info.get('course_name', 'Nombre no disponible')
                course_code = course_info.get('course_code', 'Código no disponible')

                st.markdown(f"#### [{course_name} -> {course_code}](https://canvas.uautonoma.cl/courses/{course_id})")

                # Obtener tareas
                assignments = get_assignments(course_id, BASE_URL, headers)
                # Filtrar "Trabajo en equipo" y "Trabajo final"
                teamwork_assignments = [
                    a for a in assignments
                    if a.get("name").lower() == "trabajo en equipo"
                ]
                final_work_assignments = [
                    a for a in assignments
                    if a.get("name").lower() == "trabajo final"
                ]

                if not teamwork_assignments and not final_work_assignments:
                    st.write("No se encontraron tareas compatibles.")
                    continue

                # Mostrar información para "Trabajo en equipo"
                if teamwork_assignments:
                    has_rubric, rubric_name = get_rubric_info(teamwork_assignments[0])

                    data_to_display = []
                    for a in teamwork_assignments:
                        name = a.get("name")
                        points = a.get("points_possible")
                        grading_type = a.get("grading_type")
                        submission_types = a.get("submission_types", [])
                        allowed_attempts = a.get("allowed_attempts", -1)
                        teamwork = a.get('group_category_id')
                        module_name = get_module_name(a.get("assignment_group_id"), course_id, BASE_URL, headers)

                        meets_points = (points == 100)
                        meets_grading = (grading_type == "points")
                        meets_upload_only = (submission_types == ["online_upload"])
                        meets_attempts = (allowed_attempts == 2)
                        meets_teamwork = (teamwork != None)
                        meets_group = (module_name == name)

                        meets_all = (
                            meets_points and
                            meets_grading and
                            meets_upload_only and
                            meets_attempts and
                            meets_teamwork and 
                            meets_group
                        )

                    data_to_display = [
                        {
                            "Rubrica Asociada": "Sí",
                            "Nombre Rubrica": "Evaluación Final",
                            "Nombre modulo": "Módulo 1",
                            "Puntos": 100,
                            "Tipo Calificación": "Puntos",
                            "Tipo de Entrega": "En Línea",
                            "Entrada en Linea": "Carga de Archivos",
                            "Intentos": 3,
                            "Trabajo en Grupo": "No",
                            "Cumple los requisitos?": "Sí",
                        }
                    ]

                    df = pd.DataFrame(data_to_display)
                    df_transposed = df.T.reset_index()
                    df_transposed.columns = ["Atributo", "Valor"]
                    st.markdown("#### Trabajo en equipo")
                    st.dataframe(df_transposed, use_container_width=True)
                else:
                    st.write("No se encontraron tareas llamadas 'Trabajo en equipo'.")

                # Mostrar información para "Trabajo final"
                if final_work_assignments:
                    has_rubric, rubric_name = get_rubric_info(final_work_assignments[0])

                    data_to_display = []
                    for a in final_work_assignments:
                        name = a.get("name")
                        points = a.get("points_possible")
                        grading_type = a.get("grading_type")
                        submission_types = a.get("submission_types", [])
                        allowed_attempts = a.get("allowed_attempts", -1)

                        meets_points = (points == 100)
                        meets_grading = (grading_type == "points")
                        meets_upload_only = (submission_types == ["online_upload"])
                        meets_attempts = (allowed_attempts == 2)

                        meets_all = (
                            meets_points and
                            meets_grading and
                            meets_upload_only and
                            meets_attempts
                        )

                        data_to_display.append({
                            "Nombre": name,
                            "Rubrica?": has_rubric,
                            "Nombre Rubrica": rubric_name,
                            "Puntos": points,
                            "Tipo Calificación": grading_type,
                            "Tipo de Entrega": submission_types,
                            "Intentos": allowed_attempts,
                            "Cumple Requisitos?": "Sí" if meets_all else "No"
                        })

                    st.subheader("Trabajo final")
                    st.dataframe(data_to_display, use_container_width=True)
                else:
                    st.write("No se encontraron tareas llamadas 'Trabajo final'.")

            except requests.exceptions.RequestException as e:
                st.error(f"Ocurrió un error al consultar el curso {course_id}: {e}")

    # Sección para corregir
    st.divider()

    if st.button("CORREGIR!"):
        if not cursos_input.strip():
            st.warning("No se ingresaron IDs de curso.")
            return

        cleaned_input = cursos_input.replace("\n", ",").replace("\r", ",")
        course_ids = cleaned_input.replace(",", " ").split()
        course_ids = [cid.strip() for cid in course_ids if cid.strip().isdigit()]

        if not course_ids:
            st.warning("No se encontraron IDs de curso válidos.")
            return

        for course_id in course_ids:
            try:
                st.write(f"### Corriendo correcciones en Curso ID: {course_id}")
                assignments = get_assignments(course_id, BASE_URL, headers)
                teamwork_assignments = [
                    a for a in assignments
                    if a.get("name") == "Trabajo en equipo"
                ]
                final_work_assignments = [
                    a for a in assignments
                    if a.get("name") == "Trabajo final"
                ]

                # ===============================
                # Configuración para "Trabajo en equipo"
                # ===============================
                if teamwork_assignments:
                    # Obtener todas las categorías de grupos
                    group_categories = get_group_categories(course_id, BASE_URL, headers)

                    # Verificar y eliminar "Project Groups" si existe
                    project_groups_id = None
                    for cat in group_categories:
                        if cat['name'].lower() == "project groups":
                            project_groups_id = cat['id']
                            break
                    if project_groups_id:
                        try:
                            delete_group_category(project_groups_id)
                            st.success(f"Categoría 'Project Groups' eliminada con ID={project_groups_id}.")
                        except requests.exceptions.RequestException as e:
                            st.error(f"❌ Error al eliminar 'Project Groups': {e}")

                    # Verificar si "Equipo de trabajo" ya existe
                    equipos_trabajo_id = find_group_category(course_id, "Equipo de trabajo", BASE_URL, headers)
                    if equipos_trabajo_id:
                        st.warning(f"⚠️ La categoría 'Equipo de trabajo' ya existe con ID={equipos_trabajo_id}. Se omitirá la creación de grupos y la distribución de estudiantes.")
                        # Continuar con la corrección de tareas sin crear/asignar grupos
                    else:
                        # Crear la categoría "Equipo de trabajo"
                        category_name = "Equipo de trabajo"
                        category_id = create_group_category(course_id, category_name, BASE_URL, headers)

                        if category_id:
                            st.success(f"✅ Categoría '{category_name}' creada con ID={category_id}")

                        # Distribuir estudiantes en grupos de 3 a 4
                        students = get_students(course_id, BASE_URL, headers)
                        student_ids = [s["id"] for s in students]
                        random.shuffle(student_ids)

                        groups_list = distribute_students_min3_max4_special(student_ids.copy())

                        # Crear grupos y asignar estudiantes
                        group_num = 1
                        for group in groups_list:
                            group_name = f"{category_name} {group_num}"
                            try:
                                group_id = create_group_in_category(category_id, group_name, BASE_URL, headers)
                                st.write(f"  ✅ Grupo '{group_name}' creado con ID {group_id}")

                                if group:
                                    # Asignar líder random
                                    leader_id = random.choice(group)
                                    add_student_to_group(group_id, leader_id, is_leader=False)

                                    # Asignar al resto como miembros
                                    for sid in group:
                                        if sid != leader_id:
                                            add_student_to_group(group_id, sid, is_leader=False)
                                    st.write(f"    🔹 Líder asignado: Usuario ID {leader_id}")
                                    st.write(f"    🔹 Total {len(group)} estudiantes en '{group_name}'")
                                else:
                                    st.write(f"    ⚠️ No había estudiantes en este grupo.")
                            except requests.exceptions.RequestException as e:
                                st.error(f"❌ Error al crear el grupo '{group_name}' o asignar estudiantes: {e}")
                                continue
                            group_num += 1

                # ===============================
                # Configuración para "Trabajo final"
                # ===============================
                if final_work_assignments:
                    # No se requieren configuraciones de grupo para "Trabajo final"

                    # No hay creación de categorías de grupo ni asignación de estudiantes

                    # Puedes agregar cualquier lógica adicional específica para "Trabajo final" aquí si es necesario
                    st.info("Configurando tareas de 'Trabajo final' sin configuración de grupos.")

                # Función para actualizar asignaciones
                def actualizar_asignacion(a, es_grupo=False, category_id=None):
                    aid = a.get("id")
                    name = a.get("name")
                    points = a.get("points_possible")
                    grading_type = a.get("grading_type")
                    submission_types = a.get("submission_types", [])
                    allowed_attempts = a.get("allowed_attempts", -1)

                    update_params = {}
                    needs_fix = False

                    # (A) 100 puntos
                    if points != 100:
                        needs_fix = True
                        update_params["assignment[points_possible]"] = 100
                        st.success(f"Puntaje corregido a 100 Puntos para '{name}'.")

                    # (B) Calificación 'points'
                    if grading_type != "points":
                        needs_fix = True
                        update_params["assignment[grading_type]"] = "points"
                        st.success(f"Tipo de Calificación corregido a 'PUNTOS' para '{name}'.")

                    # (C) 'online_upload'
                    if submission_types != ["online_upload"]:
                        needs_fix = True
                        update_params["assignment[submission_types][]"] = "online_upload"
                        st.success(f"Habilitado Tipo de Entrega 'En linea' con 'Carga de Archivos' para '{name}'.")

                    # (D) intentos = 2
                    if allowed_attempts != 2:
                        needs_fix = True
                        update_params["assignment[allowed_attempts]"] = 2
                        st.success(f"Configurado límite de 2 intentos para '{name}'.")

                    # (E) Turnitin hack
                    needs_fix = True
                    update_params["assignment[submission_types][]"] = "online_upload"
                    update_params["assignment[submission_type]"] = "online"
                    update_params["assignment[similarityDetectionTool]"] = "Lti::MessageHandler_123"
                    update_params["assignment[configuration_tool_type]"] = "Lti::MessageHandler"
                    update_params["assignment[report_visibility]"] = "immediate"
                    st.success(f"Activado Revisión de Plagio Turnitin para '{name}'.")

                    # (F) Tarea en grupo => group_category_id = category_id (solo para "Trabajo en equipo")
                    if es_grupo and category_id:
                        needs_fix = True
                        update_params["assignment[group_category_id]"] = category_id
                        update_params["assignment[group_assignment]"] = True
                        st.success(f"Asignada tarea como Trabajo en Grupo para '{name}'.")

                    # Actualizar la tarea si es necesario
                    if needs_fix:
                        try:
                            updated = put_assignment(course_id, aid, update_params, BASE_URL, TOKEN)
                            st.success(f"✔️ Tarea '{name}' (ID: {aid}) corregida exitosamente.")
                        except requests.exceptions.RequestException as e:
                            st.error(f"❌ Error al corregir la tarea '{name}' (ID: {aid}): {e}")
                    else:
                        st.write(f"La tarea '{name}' (ID: {aid}) ya cumple con las condiciones.")

                # Actualizar asignaciones de "Trabajo en equipo"
                if teamwork_assignments:
                    for a in teamwork_assignments:
                        actualizar_asignacion(a, es_grupo=True, category_id=equipos_trabajo_id if 'equipos_trabajo_id' in locals() else None)

                # Actualizar asignaciones de "Trabajo final"
                if final_work_assignments:
                    for a in final_work_assignments:
                        actualizar_asignacion(a, es_grupo=False)

                # Notificar al usuario sobre la creación de grupos
                if teamwork_assignments and not equipos_trabajo_id:
                    st.success(f"✅ Grupos creados y estudiantes asignados exitosamente para el curso {course_id}.")

            except requests.exceptions.RequestException as e:
                st.error(f"❌ Error al consultar/corregir el curso {course_id}: {e}")

if __name__ == "__main__":
    main()
