import requests
from collections import defaultdict


def get_course_information(course_id: int, canvas_base_url: str, headers: dict) -> dict:
    
    try:
        # 1) Obtener la información del curso
        course_url = f"{canvas_base_url}/courses/{course_id}"
        resp_course = requests.get(course_url, headers=headers)
        resp_course.raise_for_status()  # Lanza excepción si no es 2xx
        course_data = resp_course.json()

        # Extraer los campos deseados
        course_name = course_data.get("name", "")
        course_code = course_data.get("course_code", "")
        sis_course_id = course_data.get("sis_course_id")  # Puede ser None
        start_at = course_data.get("start_at")            # Fecha de inicio
        subaccount_id = course_data.get("account_id")      # ID de la subcuenta

        # 2) Obtener la información de la subcuenta
        subaccount_name = None
        if subaccount_id is not None:
            account_url = f"{canvas_base_url}/accounts/{subaccount_id}"
            resp_account = requests.get(account_url, headers=headers)
            if resp_account.status_code == 200:
                account_data = resp_account.json()
                subaccount_name = account_data.get("name")

        # 3) Retornar el diccionario con la información solicitada
        return {
            "course_name": course_name,
            "course_code": course_code,
            "sis_course_id": sis_course_id,
            "start_at": start_at,
            "subaccount_id": subaccount_id,
            "subaccount_name": subaccount_name
        }

    except requests.exceptions.RequestException as e:
        # Manejo de errores de red o HTTP
        raise ValueError(f"Error al obtener la información del curso o subcuenta: {e}")
    
    
def get_students(course_id: str, canvas_base_url: str, headers: dict) -> dict:
    url = f"{canvas_base_url}/courses/{course_id}/students"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def get_assignments(course_id: str, canvas_base_url: str, headers: dict) -> dict:
    url = f"{canvas_base_url}/courses/{course_id}/assignments"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def put_assignment(course_id: str, assignment_id: str, params: dict, canvas_base_url: str, token: str ) -> dict:
    url = f"{canvas_base_url}/courses/{course_id}/assignments/{assignment_id}"
    local_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.put(url, headers=local_headers, data=params)
    response.raise_for_status()
    return response.json()


def create_group_category(course_id: str, category_name: str, canvas_base_url: str, headers: dict) -> dict:
    url = f"{canvas_base_url}/courses/{course_id}/group_categories"
    data = {
        "name": category_name,
        "self_signup": "disabled",
        "auto_leader": "random",
    }
    resp = requests.post(url, headers=headers, data=data)
    resp.raise_for_status()
    return resp.json()["id"]  # group_category_id


def create_group_in_category(category_id: int, group_name: str, canvas_base_url: str, headers: dict) -> dict:
    url = f"{canvas_base_url}/group_categories/{category_id}/groups"
    data = {
        "name": group_name
    }
    resp = requests.post(url, headers=headers, data=data)
    resp.raise_for_status()
    return resp.json()["id"] # group_id


def distribute_students_min3_max4_special(student_ids):
    groups = []
    i = 0
    n = len(student_ids)

    # 1) Agrupamos en bloques de 4
    while i < n:
        chunk = student_ids[i:i+4]
        groups.append(chunk)
        i += 4

    # Verificamos el size del último
    if len(groups) < 2:
        return groups  # No hay penúltimo ni antepenúltimo

    last_group = groups[-1]
    if len(last_group) == 1:
        # Quiero sacar 1 del penúltimo (si tiene 4) y 1 del antepenúltimo (si tiene 4)
        # para formar 3 en el último
        if len(groups) >= 3:
            second_last = groups[-2]
            third_last = groups[-3]
            # Solo si second_last y third_last tienen 4
            if len(second_last) == 4 and len(third_last) == 4:
                # mover 1 del second_last
                last_group.append(second_last.pop())
                # mover 1 del third_last
                last_group.append(third_last.pop())
                groups[-2] = second_last
                groups[-3] = third_last
                groups[-1] = last_group
            else:
                # No se puede, quedará con 1
                pass
        else:
            # No hay antepenúltimo, quedará con 1
            pass
    elif len(last_group) == 2:
        # Quita 1 del penúltimo si tiene 4 => quedarán 3 y 3
        second_last = groups[-2]
        if len(second_last) == 4:
            last_group.append(second_last.pop())
            groups[-2] = second_last
            groups[-1] = last_group
        # si no, se queda con 2

    return groups


def get_group_categories(course_id: str, canvas_base_url: str, headers: dict) -> dict:
    url = f"{canvas_base_url}/courses/{course_id}/group_categories"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def find_group_category(course_id: str, category_name: str, canvas_base_url: str, headers: dict):
    categories = get_group_categories(course_id, canvas_base_url, headers)
    for cat in categories:
        if cat['name'].lower() == category_name.lower():
            return cat['id']
    return None


def delete_group_category(category_id: int, canvas_base_url: str, headers: dict):
    url = f"{canvas_base_url}/group_categories/{category_id}"
    response = requests.delete(url, headers=headers)
    if response.status_code == 204:
        return True
    else:
        response.raise_for_status()
        

def get_rubric_info(assignment):
    if assignment.get("rubric_settings"):
        has_rubric = "Si"
        rubric_name = assignment["rubric_settings"]["title"]
    else:
        has_rubric = "No"
        rubric_name = "Sin Rubrica"
    return has_rubric, rubric_name


def get_module_name(assignment_group_id, course_id: str, canvas_base_url: str, headers: dict):
    url = f"{canvas_base_url}/courses/{course_id}/assignment_groups/{assignment_group_id}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["name"]
    else:
        print(response.status_code)
        None

def modify_module_name(assignment_group_id, assignment_name, course_id: str, canvas_base_url: str, token: str):
    payload = {
        "name": assignment_name
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    response = requests.put(f"{canvas_base_url}/courses/{course_id}/assignment_groups/{assignment_group_id}", headers=headers, json=payload)
    if response.status_code == 200:
        return True
    else:
        return False    
