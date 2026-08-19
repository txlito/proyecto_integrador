import ctypes
import sys
import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from abc import ABC, abstractmethod
from typing import List, Optional
from pymongo import MongoClient
from bson import ObjectId


#CONFIGURACIÓN DE ALTA RESOLUCIÓN
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# CAPA DE DOMINIO Y MODELOS 
class Usuario(ABC):
    def __init__(self, id_usuario: str, nombre_usuario: str, nombre_completo: str, rol: str):
        self.id_usuario = id_usuario
        self.nombre_usuario = nombre_usuario
        self.nombre_completo = nombre_completo
        self.rol = rol

class Profesor(Usuario):
    def __init__(self, id_usuario: str, nombre_usuario: str, nombre_completo: str, materia_asignada: str, id_grupo: str):
        super().__init__(id_usuario, nombre_usuario, nombre_completo, rol="teacher")
        self.materia_asignada = materia_asignada
        self.id_grupo = id_grupo

    def puede_editar_materia(self, materia: str) -> bool:
        return self.materia_asignada == materia

    def puede_ver_calificaciones_grupo(self) -> bool:
        return False

class ProfesorTutor(Profesor):
    def __init__(self, id_usuario: str, nombre_usuario: str, nombre_completo: str, materia_asignada: str, id_grupo: str):
        super().__init__(id_usuario, nombre_usuario, nombre_completo, materia_asignada, id_grupo)
        self.rol = "tutor"

    def puede_ver_calificaciones_grupo(self) -> bool:
        return True

class Alumno(Usuario):
    def __init__(self, id_usuario: str, nombre_usuario: str, nombre_completo: str, id_grupo: str):
        super().__init__(id_usuario, nombre_usuario, nombre_completo, rol="student")
        self.id_grupo = id_grupo


# CAPA DE INFRAESTRUCTURA
class MongoConnection:
    _instance = None

    def __new__(cls, uri="mongodb+srv://txlito:Irving11@cluster0.ha23c3n.mongodb.net/?appName=Cluster0", db_name="proyecto_completo"):
        if cls._instance is None:
            cls._instance = super(MongoConnection, cls).__new__(cls)
            cls._instance.client = MongoClient(uri, serverSelectionTimeoutMS=30000)
            cls._instance.db = cls._instance.client[db_name]
        return cls._instance


class IRepositorioUsuario(ABC):
    @abstractmethod
    def buscar_por_nombre_usuario(self, nombre_usuario: str) -> Optional[dict]:
        pass

    @abstractmethod
    def obtener_contactos_por_rol(self, rol_actual: str) -> List[dict]:
        pass


class IRepositorioCalificacion(ABC):
    @abstractmethod
    def obtener_por_materia(self, materia: str) -> List[dict]:
        pass

    @abstractmethod
    def obtener_por_grupo(self, id_grupo: str) -> List[dict]:
        pass

    @abstractmethod
    def obtener_por_alumno(self, nombre_estudiante: str) -> List[dict]:
        pass

    @abstractmethod
    def actualizar_unidad(self, id_estudiante: str, materia: str, unidad: str, valor: float):
        pass

    @abstractmethod
    def actualizar_examen(self, id_estudiante: str, materia: str, tipo_examen: str, valor: float):
        pass


class IRepositorioMensajeria(ABC):
    @abstractmethod
    def insertar(self, remitente: str, destinatario: str, contenido: str):
        pass
    @abstractmethod
    def obtener_historial(self, u1: str, u2: str) -> List[dict]:
        pass


class RepositorioMongo(IRepositorioUsuario, IRepositorioCalificacion, IRepositorioMensajeria):
    def __init__(self):
        self.db = MongoConnection().db
        self.coleccion_usuarios = self.db["usuarios"]          
        self.coleccion_alumnos = self.db["usuarios_alumnos"]  
        self.coleccion_calificaciones = self.db["grades"]
        self.coleccion_mensajes = self.db["mensajes"]

    def buscar_por_nombre_usuario(self, nombre_usuario: str) -> Optional[dict]:
        doc_alumno = self.coleccion_alumnos.find_one({"username": nombre_usuario})
        if doc_alumno:
            doc_alumno["_id"] = str(doc_alumno["_id"])
            doc_alumno["role"] = "student"
            doc_alumno["password"] = doc_alumno.get("password", "")

            if "group_id" not in doc_alumno:
                doc_alumno["group_id"] = "1"

            partes = nombre_usuario.split('.')
            if len(partes) >= 2:
                doc_alumno["full_name"] = f"{partes[0].capitalize()} {partes[1].capitalize()}"
            else:
                doc_alumno["full_name"] = nombre_usuario.capitalize()

            return doc_alumno

        doc_prof = self.coleccion_usuarios.find_one({"username": nombre_usuario})
        if doc_prof:
            doc_prof["_id"] = str(doc_prof["_id"])
            if "full_name" not in doc_prof:
                doc_prof["full_name"] = doc_prof.get("nombre", doc_prof.get("nombre_completo", nombre_usuario))
            return doc_prof
        return None

    def obtener_contactos_por_rol(self, rol_actual: str) -> List[dict]:
        resultados = []
        if rol_actual == "student":
            cursor = self.coleccion_usuarios.find({}, {"password": 0})
            for doc in cursor:
                doc["_id"] = str(doc["_id"])
                if "full_name" not in doc:
                    doc["full_name"] = doc.get("nombre", doc.get("nombre_completo", doc.get("username", "")))
                resultados.append(doc)
        else:
            cursor = self.coleccion_alumnos.find()
            for doc in cursor:
                doc["_id"] = str(doc["_id"])
                usr = doc.get("username", "")
                doc["username"] = usr

                partes = usr.split('.')
                if len(partes) >= 2:
                    doc["full_name"] = f"{partes[0].capitalize()} {partes[1].capitalize()}"
                else:
                    doc["full_name"] = usr.capitalize() if usr else "Alumno"

                resultados.append(doc)
        return resultados

    def obtener_por_materia(self, materia: str) -> List[dict]:
        cursor = self.coleccion_calificaciones.find({"subject": materia})
        resultados = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            resultados.append(doc)
        return resultados

    def obtener_por_grupo(self, id_grupo: str) -> List[dict]:
        import unicodedata
        import re

        def limpiar_texto(texto):
            if not texto:
                return ""
            nfkd = unicodedata.normalize('NFKD', texto)
            return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower()

        patron_grupo = re.escape(id_grupo.strip()) if id_grupo else ""

        # 1. Obtener todos los registros de calificaciones del grupo
        query = {
            "$or": [
                {"group_id": {"$regex": f"^{patron_grupo}$", "$options": "i"}},
                {"id_grupo": {"$regex": f"^{patron_grupo}$", "$options": "i"}}
            ]
        }
        cursor_grades = list(self.coleccion_calificaciones.find(query))
        for doc in cursor_grades:
            doc["_id"] = str(doc["_id"])

        # Agrupar por student_name original de calificaciones
        mapa_por_nombre_grades = {}
        for doc in cursor_grades:
            s_name = doc.get("student_name", "").strip()
            if s_name:
                if s_name not in mapa_por_nombre_grades:
                    mapa_por_nombre_grades[s_name] = []
                mapa_por_nombre_grades[s_name].append(doc)

        # 2. Obtener todos los alumnos de usuarios_alumnos para asegurar orden y cobertura completa
        cursor_alumnos = list(self.coleccion_alumnos.find())
        estudiantes_procesados = []

        for alumno_doc in cursor_alumnos:
            usr = alumno_doc.get("username", "")
            partes_usr = [p.lower() for p in usr.split('.') if p]

            docs_alumno = []
            nombre_mostrar = usr.capitalize()

            for s_name, docs in mapa_por_nombre_grades.items():
                s_name_clean = limpiar_texto(s_name)
                # Verifica que todas las partes del username estén contenidas en el nombre de grades
                if partes_usr and all(parte in s_name_clean for parte in partes_usr):
                    docs_alumno.extend(docs)
                    nombre_mostrar = s_name  # Usa el nombre real completo

            if docs_alumno:
                docs_alumno_sorted = sorted(docs_alumno, key=lambda x: x.get("subject", ""))
                estudiantes_procesados.append((nombre_mostrar, docs_alumno_sorted))
            else:
                partes = usr.split('.')
                if len(partes) >= 2:
                    nombre_completo = f"{partes[0].capitalize()} {partes[1].capitalize()}"
                else:
                    nombre_completo = usr.capitalize()

                fila_vacia = [{
                    "_id": str(alumno_doc["_id"]),
                    "student_name": nombre_completo,
                    "subject": "Sin materias registradas",
                    "group_id": id_grupo,
                    "units": {"u1": "-", "u2": "-", "u3": "-", "u4": "-"},
                    "exams": {"ordinario": "-", "remedial": "-", "extraordinario": "-", "ultima_oportunidad": "-"}
                }]
                estudiantes_procesados.append((nombre_completo, fila_vacia))

        # 3. Ordenar todos los estudiantes alfabéticamente por su nombre
        estudiantes_procesados = sorted(estudiantes_procesados, key=lambda x: x[0])

        resultados_finales = []
        for nombre, docs in estudiantes_procesados:
            resultados_finales.extend(docs)

        return resultados_finales

    def obtener_por_alumno(self, nombre_estudiante: str) -> List[dict]:
        import re
        # Limpiamos y preparamos una búsqueda flexible ignorando mayúsculas, minúsculas y acentos opcionales
        patron = re.escape(nombre_estudiante.strip())

        query = {
            "$or": [
                {"student_name": {"$regex": f"^{patron}$", "$options": "i"}},
                {"username": {"$regex": f"^{patron}$", "$options": "i"}},
                {"email": {"$regex": f"^{patron}$", "$options": "i"}}
            ]
        }

        cursor = self.coleccion_calificaciones.find(query)
        resultados = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            resultados.append(doc)

        # Si por alguna razón la búsqueda exacta estricta no arrojó resultados, intentamos buscar de forma parcial por el primer nombre y apellido
        if not resultados and " " in nombre_estudiante:
            partes = nombre_estudiante.split()
            query_parcial = {
                "$or": [
                    {"student_name": {"$regex": partes[0], "$options": "i"}},
                    {"student_name": {"$regex": partes[-1], "$options": "i"}}
                ]
            }
            cursor_parcial = self.coleccion_calificaciones.find(query_parcial)
            for doc in cursor_parcial:
                doc["_id"] = str(doc["_id"])
                if doc not in resultados:
                    resultados.append(doc)

        return resultados

    def actualizar_unidad(self, id_estudiante: str, materia: str, unidad: str, valor: float):
        self.coleccion_calificaciones.update_one(
            {"_id": ObjectId(id_estudiante), "subject": materia},
            {"$set": {f"units.{unidad}": valor}}
        )

    def actualizar_examen(self, id_estudiante: str, materia: str, tipo_examen: str, valor: float):
        datos_actualizacion = {f"exams.{tipo_examen}": valor}
        if tipo_examen == "ultima_oportunidad":
            datos_actualizacion["metadata.ultima_oportunidad_usada"] = True

        self.coleccion_calificaciones.update_one(
            {"_id": ObjectId(id_estudiante), "subject": materia},
            {"$set": datos_actualizacion}
        )

    def insertar(self, remitente: str, destinatario: str, contenido: str):
        mensaje = {
            "remitente": remitente,
            "destinatario": destinatario,
            "contenido": contenido,
            "fecha": datetime.datetime.now()
        }
        self.coleccion_mensajes.insert_one(mensaje)

    def obtener_historial(self, u1: str, u2: str) -> List[dict]:
        query = {
            "$or": [
                {"remitente": u1, "destinatario": u2},
                {"remitente": u2, "destinatario": u1}
            ]
        }
        cursor = self.coleccion_mensajes.find(query).sort("fecha", 1)
        resultados = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            resultados.append(doc)
        return resultados


# LÓGICA DE NEGOCIO
class ServicioAutenticacion:
    def __init__(self, repositorio_usuario: IRepositorioUsuario):
        self.repositorio_usuario = repositorio_usuario

    def autenticar(self, nombre_usuario: str, contraseña: str) -> Usuario:
        datos_usuario = self.repositorio_usuario.buscar_por_nombre_usuario(nombre_usuario)
        if not datos_usuario or datos_usuario.get("password") != contraseña:
            raise ValueError("Credenciales inválidas. Verifique usuario y contraseña.")

        rol = datos_usuario.get("role")
        nombre_completo = datos_usuario.get("full_name", datos_usuario.get("nombre", nombre_usuario))

        if rol == "tutor":
            return ProfesorTutor(datos_usuario["_id"], datos_usuario["username"], nombre_completo, datos_usuario.get("assigned_subject", ""), datos_usuario.get("group_id", ""))
        elif rol == "teacher":
            return Profesor(datos_usuario["_id"], datos_usuario["username"], nombre_completo, datos_usuario.get("assigned_subject", ""), datos_usuario.get("group_id", ""))
        elif rol == "student":
            return Alumno(datos_usuario["_id"], datos_usuario["username"], nombre_completo, datos_usuario.get("group_id", ""))
        else:
            raise PermissionError("Rol no autorizado.")


class ServicioCalificacion:
    def __init__(self, repositorio_calificacion: IRepositorioCalificacion):
        self.repositorio_calificacion = repositorio_calificacion

    def obtener_calificaciones_materia(self, materia: str) -> List[dict]:
        return self.repositorio_calificacion.obtener_por_materia(materia)

    def obtener_calificaciones_grupo(self, id_grupo: str) -> List[dict]:
        return self.repositorio_calificacion.obtener_por_grupo(id_grupo)

    def obtener_calificaciones_alumno(self, nombre_estudiante: str) -> List[dict]:
        return self.repositorio_calificacion.obtener_por_alumno(nombre_estudiante)

    def actualizar_calificacion(self, id_estudiante: str, materia: str, categoria: str, campo: str, valor: float, usuario_actual: Usuario):
        if not isinstance(usuario_actual, Profesor) or not usuario_actual.puede_editar_materia(materia):
            raise PermissionError(f"No tienes permisos para editar la materia {materia}.")

        if not (0 <= valor <= 10):
            raise ValueError("La calificación debe estar entre 0 y 10.")

        if categoria == "units":
            self.repositorio_calificacion.actualizar_unidad(id_estudiante, materia, campo, valor)
        elif categoria == "exams":
            if campo == "ultima_oportunidad":
                registros = self.repositorio_calificacion.obtener_por_materia(materia)
                registro = next((r for r in registros if r["_id"] == id_estudiante), None)
                if registro and registro.get("metadata", {}).get("ultima_oportunidad_usada", False):
                    raise ValueError("Regla de negocio: El alumno ya utilizó su oportunidad de 'Última Oportunidad' en esta materia.")

            self.repositorio_calificacion.actualizar_examen(id_estudiante, materia, campo, valor)


class ServicioMensajeria:
    def __init__(self, repositorio_mensajeria: IRepositorioMensajeria, repositorio_usuario: IRepositorioUsuario):
        self.repositorio_mensajeria = repositorio_mensajeria
        self.repositorio_usuario = repositorio_usuario

    def obtener_contactos(self, usuario_actual: Usuario) -> List[dict]:
        return self.repositorio_usuario.obtener_contactos_por_rol(usuario_actual.rol)

    def enviar_mensaje(self, remitente: str, destinatario: str, contenido: str):
        if not contenido.strip():
            raise ValueError("El mensaje no puede estar vacío.")
        self.repositorio_mensajeria.insertar(remitente, destinatario, contenido)

    def ver_conversacion(self, u1: str, u2: str) -> List[dict]:
        return self.repositorio_mensajeria.obtener_historial(u1, u2)


#VISTAS 
def aplicar_tema_personalizado():
    style = ttk.Style()
    style.theme_use("clam")

    BG_DARK = "#0F172A"        
    SURFACE = "#1E293B"        
    PRIMARY = "#38BDF8"        
    SECONDARY = "#818CF8"      
    TEXT_MAIN = "#F1F5F9"      
    TEXT_SEC = "#94A3B8"       

    style.configure(".", background=BG_DARK, foreground=TEXT_MAIN, font=("Segoe UI", 10))
    style.configure("TFrame", background=BG_DARK)
    style.configure("Card.TFrame", background=SURFACE)

    style.configure("TLabel", background=BG_DARK, foreground=TEXT_MAIN, font=("Segoe UI", 10))
    style.configure("Secondary.TLabel", background=BG_DARK, foreground=TEXT_SEC, font=("Segoe UI", 9))
    style.configure("Heading.TLabel", background=BG_DARK, foreground=PRIMARY, font=("Segoe UI", 16, "bold"))

    style.configure("TButton", background=SURFACE, foreground=TEXT_MAIN, bordercolor=PRIMARY, font=("Segoe UI", 10), padding=6)
    style.map("TButton",
        background=[('active', PRIMARY), ('pressed', SECONDARY)],
        foreground=[('active', BG_DARK), ('pressed', BG_DARK)]
    )

    style.configure("TEntry", fieldbackground=SURFACE, foreground=TEXT_MAIN, insertcolor=TEXT_MAIN)
    style.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE, foreground=TEXT_MAIN, selectbackground=PRIMARY)

    style.configure("TNotebook", background=BG_DARK, borderwidth=0)
    style.configure("TNotebook.Tab", background=SURFACE, foreground=TEXT_SEC, padding=[12, 8], font=("Segoe UI", 10, "bold"))
    style.map("TNotebook.Tab",
        background=[('selected', PRIMARY), ('active', SURFACE)],
        foreground=[('selected', BG_DARK), ('active', TEXT_MAIN)]
    )

    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT_MAIN, rowheight=28, font=("Segoe UI", 9))
    style.configure("Treeview.Heading", background=SURFACE, foreground=PRIMARY, font=("Segoe UI", 10, "bold"), relief="flat")
    style.map("Treeview", background=[('selected', PRIMARY)], foreground=[('selected', BG_DARK)])


class VistaInicioSesion(ttk.Frame):
    def __init__(self, padre, servicio_autenticacion, al_exito):
        super().__init__(padre)
        self.servicio_autenticacion = servicio_autenticacion
        self.al_exito = al_exito
        self.pack(fill=tk.BOTH, expand=True)
        self._crear_componentes()

    def _crear_componentes(self):
        contenedor = ttk.Frame(self, style="Card.TFrame", padding=35)
        contenedor.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        ttk.Label(contenedor, text="Portal Académico", style="Heading.TLabel").grid(row=0, column=0, columnspan=2, pady=(0, 20))

        ttk.Label(contenedor, text="Usuario:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.entrada_usuario = ttk.Entry(contenedor, font=("Segoe UI", 10), width=25)
        self.entrada_usuario.grid(row=1, column=1, pady=5, padx=5)

        ttk.Label(contenedor, text="Contraseña:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.entrada_contraseña = ttk.Entry(contenedor, font=("Segoe UI", 10), show="*", width=25)
        self.entrada_contraseña.grid(row=2, column=1, pady=5, padx=5)

        btn = ttk.Button(contenedor, text="Ingresar", command=self._iniciar_sesion)
        btn.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(20, 0))

    def _iniciar_sesion(self):
        u = self.entrada_usuario.get().strip()
        p = self.entrada_contraseña.get().strip()
        if not u or not p:
            messagebox.showwarning("Campos vacíos", "Ingrese usuario y contraseña.")
            return
        try:
            objeto_usuario = self.servicio_autenticacion.autenticar(u, p)
            self.al_exito(objeto_usuario)
        except Exception as e:
            messagebox.showerror("Error de Acceso", str(e))


class DialogoEditarCalificacion(tk.Toplevel):
    def __init__(self, padre, id_estudiante, nombre_estudiante, materia, servicio_calificacion, usuario_actual, callback_guardado):
        super().__init__(padre)
        self.title("Modificar Calificación")
        self.geometry("350x290")
        self.resizable(False, False)
        self.transient(padre)
        self.grab_set()
        self.configure(bg="#0F172A")

        self.id_estudiante = id_estudiante
        self.materia = materia
        self.servicio_calificacion = servicio_calificacion
        self.usuario_actual = usuario_actual
        self.callback_guardado = callback_guardado

        self._crear_componentes(nombre_estudiante)

    def _crear_componentes(self, nombre_estudiante):
        marco = ttk.Frame(self, padding=20)
        marco.pack(fill=tk.BOTH, expand=True)

        ttk.Label(marco, text=f"Alumno: {nombre_estudiante}", font=("Segoe UI", 10, "bold"), foreground="#38BDF8").pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(marco, text="Seleccione el campo a modificar:").pack(anchor=tk.W)

        self.variable_campo = tk.StringVar(value="u1")
        campos = [
            ("Unidad 1", "u1"), ("Unidad 2", "u2"), ("Unidad 3", "u3"), ("Unidad 4", "u4"),
            ("Ordinario", "ordinario"), ("Remedial", "remedial"), 
            ("Extraordinario", "extraordinario"), ("Última Oportunidad", "ultima_oportunidad")
        ]

        self.combo = ttk.Combobox(marco, textvariable=self.variable_campo, state="readonly", font=("Segoe UI", 9))
        self.combo['values'] = [f[0] for f in campos]
        self.mapa_campos = {f[0]: f[1] for f in campos}
        self.combo.current(0)
        self.combo.pack(fill=tk.X, pady=(5, 15))

        ttk.Label(marco, text="Nueva Calificación (0 - 10):").pack(anchor=tk.W)
        self.entrada_valor = ttk.Entry(marco, font=("Segoe UI", 10))
        self.entrada_valor.pack(fill=tk.X, pady=(5, 20))

        marco_botones = ttk.Frame(marco)
        marco_botones.pack(fill=tk.X)

        ttk.Button(marco_botones, text="Guardar", command=self._guardar).pack(side=tk.RIGHT, padx=5)
        ttk.Button(marco_botones, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT)

    def _guardar(self):
        texto_seleccionado = self.variable_campo.get()
        clave_campo = self.mapa_campos[texto_seleccionado]
        categoria = "units" if clave_campo.startswith("u") else "exams"

        try:
            val = float(self.entrada_valor.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Ingrese un valor numérico válido.")
            return

        try:
            self.servicio_calificacion.actualizar_calificacion(self.id_estudiante, self.materia, categoria, clave_campo, val, self.usuario_actual)
            messagebox.showinfo("Éxito", "Calificación actualizada correctamente.")
            self.callback_guardado()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error de Negocio", str(e))


class VistaTablaCalificaciones(ttk.Frame):
    def __init__(self, padre, servicio_calificacion, usuario_actual, materia_a_editar="", es_editable=True, es_vista_grupo=False):
        super().__init__(padre)
        self.servicio_calificacion = servicio_calificacion
        self.usuario_actual = usuario_actual
        self.materia_a_editar = materia_a_editar
        self.es_editable = es_editable
        self.es_vista_grupo = es_vista_grupo
        self.cache_registros = {}
        self._crear_componentes()

    def _crear_componentes(self):
        if isinstance(self.usuario_actual, Alumno):
            columnas = ("subject", "u1", "u2", "u3", "u4", "ordinario", "remedial", "extraordinario", "ultima_oportunidad")
            encabezados = {
                "subject": "Materia", "u1": "U1", "u2": "U2", "u3": "U3", "u4": "U4",
                "ordinario": "Ord.", "remedial": "Rem.", "extraordinario": "Ext.", "ultima_oportunidad": "Ult. Op."
            }
        elif self.es_vista_grupo:
            columnas = ("student_name", "subject", "u1", "u2", "u3", "u4", "ordinario", "remedial", "extraordinario", "ultima_oportunidad")
            encabezados = {
                "student_name": "Alumno", "subject": "Materia", "u1": "U1", "u2": "U2", "u3": "U3", "u4": "U4",
                "ordinario": "Ord.", "remedial": "Rem.", "extraordinario": "Ext.", "ultima_oportunidad": "Ult. Op."
            }
        else:
            columnas = ("student_name", "u1", "u2", "u3", "u4", "ordinario", "remedial", "extraordinario", "ultima_oportunidad")
            encabezados = {
                "student_name": "Alumno", "u1": "U1", "u2": "U2", "u3": "U3", "u4": "U4",
                "ordinario": "Ord.", "remedial": "Rem.", "extraordinario": "Ext.", "ultima_oportunidad": "Ult. Op."
            }

        marco_principal = ttk.Frame(self, padding=10)
        marco_principal.pack(fill=tk.BOTH, expand=True)

        self.arbol = ttk.Treeview(marco_principal, columns=columnas, show="headings", selectmode="browse")

        for col, texto in encabezados.items():
            self.arbol.heading(col, text=texto)
            anchura = 140 if col in ("student_name", "subject") else 60
            self.arbol.column(col, width=anchura, anchor=tk.CENTER if col not in ("student_name", "subject") else tk.W)

        barra_vertical = ttk.Scrollbar(marco_principal, orient=tk.VERTICAL, command=self.arbol.yview)
        self.arbol.configure(yscrollcommand=barra_vertical.set)

        self.arbol.grid(row=0, column=0, sticky=tk.NSEW)
        barra_vertical.grid(row=0, column=1, sticky=tk.NS)
        marco_principal.rowconfigure(0, weight=1)
        marco_principal.columnconfigure(0, weight=1)

        if self.es_editable and not isinstance(self.usuario_actual, Alumno) and not self.es_vista_grupo:
            marco_botones = ttk.Frame(self, padding=(10, 0))
            marco_botones.pack(fill=tk.X, pady=5)
            ttk.Button(marco_botones, text="Editar Calificación de Alumno Seleccionado", command=self._abrir_dialogo_editar).pack(side=tk.LEFT)

    def cargar_datos(self, registros: List[dict]):
        self.cache_registros = {r["_id"]: r for r in registros}
        for item in self.arbol.get_children():
            self.arbol.delete(item)

        if self.es_vista_grupo:
            registros_ordenados = sorted(registros, key=lambda x: (x.get("student_name", ""), x.get("subject", "")))
            ultimo_alumno = None

            for r in registros_ordenados:
                u = r.get("units", {})
                e = r.get("exams", {})
                nombre_actual = r.get("student_name", "-")

                col_alumno = nombre_actual if nombre_actual != ultimo_alumno else ""
                ultimo_alumno = nombre_actual

                self.arbol.insert("", tk.END, iid=r["_id"], values=(
                    col_alumno, r.get("subject", "-"),
                    u.get("u1", "-"), u.get("u2", "-"), u.get("u3", "-"), u.get("u4", "-"),
                    e.get("ordinario", "-"), e.get("remedial", "-"), e.get("extraordinario", "-"), e.get("ultima_oportunidad", "-")
                ))
        else:
            for r in registros:
                u = r.get("units", {})
                e = r.get("exams", {})
                col1 = r.get("subject", "-") if isinstance(self.usuario_actual, Alumno) else r.get("student_name", "-")

                self.arbol.insert("", tk.END, iid=r["_id"], values=(
                    col1, u.get("u1", "-"), u.get("u2", "-"), u.get("u3", "-"), u.get("u4", "-"),
                    e.get("ordinario", "-"), e.get("remedial", "-"), e.get("extraordinario", "-"), e.get("ultima_oportunidad", "-")
                ))

    def _abrir_dialogo_editar(self):
        item_seleccionado = self.arbol.selection()
        if not item_seleccionado:
            messagebox.showwarning("Selección requerida", "Por favor seleccione un alumno de la tabla.")
            return

        id_estudiante = item_seleccionado[0]
        registro = self.cache_registros.get(id_estudiante)
        if not registro:
            return

        DialogoEditarCalificacion(
            self, id_estudiante, registro.get("student_name"), self.materia_a_editar, 
            self.servicio_calificacion, self.usuario_actual, self.refrescar_datos
        )

    def refrescar_datos(self):
        if isinstance(self.usuario_actual, Alumno):
            registros_actualizados = self.servicio_calificacion.obtener_calificaciones_alumno(self.usuario_actual.nombre_completo)
        elif self.es_vista_grupo:
            registros_actualizados = self.servicio_calificacion.obtener_calificaciones_grupo(self.usuario_actual.id_grupo)
        else:
            registros_actualizados = self.servicio_calificacion.obtener_calificaciones_materia(self.materia_a_editar)
        self.cargar_datos(registros_actualizados)


class VistaMensajeria(ttk.Frame):
    def __init__(self, padre, usuario_actual, servicio_mensajeria):
        super().__init__(padre, padding=10)
        self.usuario_actual = usuario_actual
        self.servicio_mensajeria = servicio_mensajeria
        self.contacto_seleccionado = None
        self.contactos_data = []
        self._crear_disposicion()
        self._cargar_contactos()

    def _crear_disposicion(self):
        panel = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        panel.pack(fill=tk.BOTH, expand=True)

        izquierda = ttk.Frame(panel, padding=5)
        panel.add(izquierda, weight=1)

        titulo_contactos = "Alumnos del Grupo" if not isinstance(self.usuario_actual, Alumno) else "Profesores Disponibles"
        ttk.Label(izquierda, text=titulo_contactos, font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=5)

        self.arbol_contactos = ttk.Treeview(izquierda, columns=("full_name",), show="tree", selectmode="browse")
        self.arbol_contactos.pack(fill=tk.BOTH, expand=True)
        self.arbol_contactos.bind("<<TreeviewSelect>>", self._on_seleccionar_contacto)

        derecha = ttk.Frame(panel, padding=5)
        panel.add(derecha, weight=3)

        self.etiqueta_chat_titulo = ttk.Label(derecha, text="Selecciona un contacto para iniciar chat", font=("Segoe UI", 10, "bold"))
        self.etiqueta_chat_titulo.pack(anchor=tk.W, pady=5)

        self.pantalla_chat = tk.Text(derecha, wrap=tk.WORD, height=12, bg="#1E293B", fg="#F1F5F9", insertbackground="#F1F5F9", relief=tk.FLAT)
        self.pantalla_chat.pack(fill=tk.BOTH, expand=True, pady=5)
        self.pantalla_chat.config(state=tk.DISABLED)

        inferior = ttk.Frame(derecha)
        inferior.pack(fill=tk.X, pady=5)
        self.entrada_mensaje = ttk.Entry(inferior, font=("Segoe UI", 10))
        self.entrada_mensaje.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.entrada_mensaje.bind("<Return>", lambda event: self._enviar_mensaje())

        self.btn_enviar = ttk.Button(inferior, text="Enviar", command=self._enviar_mensaje, state=tk.DISABLED)
        self.btn_enviar.pack(side=tk.RIGHT)

    def _cargar_contactos(self):
        try:
            self.contactos_data = self.servicio_mensajeria.obtener_contactos(self.usuario_actual)
            for c in self.contactos_data:
                nombre = c.get("full_name", c.get("nombre", c.get("username", "Desconocido")))
                self.arbol_contactos.insert("", tk.END, iid=c["username"], values=(nombre,))
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron cargar los contactos: {str(e)}")

    def _on_seleccionar_contacto(self, event):
        seleccion = self.arbol_contactos.selection()
        if not seleccion:
            return
        username_destinatario = seleccion[0]
        self.contacto_seleccionado = next((c for c in self.contactos_data if c["username"] == username_destinatario), None)

        if self.contacto_seleccionado:
            nombre_visible = self.contacto_seleccionado.get("full_name", self.contacto_seleccionado.get("nombre", username_destinatario))
            self.etiqueta_chat_titulo.config(text=f"Chat con: {nombre_visible}")
            self.btn_enviar.config(state=tk.NORMAL)
            self._actualizar_pantalla_chat()

    def _actualizar_pantalla_chat(self):
        if not self.contacto_seleccionado:
            return

        remitente = self.usuario_actual.nombre_usuario
        destinatario = self.contacto_seleccionado["username"]

        mensajes = self.servicio_mensajeria.ver_conversacion(remitente, destinatario)

        self.pantalla_chat.config(state=tk.NORMAL)
        self.pantalla_chat.delete("1.0", tk.END)

        for m in mensajes:
            rem = m.get("remitente")
            contenido = m.get("contenido")
            etiqueta_rem = "Tú" if rem == remitente else self.contacto_seleccionado.get("full_name", self.contacto_seleccionado.get("nombre", rem))
            self.pantalla_chat.insert(tk.END, f"{etiqueta_rem}: {contenido}\n")

        self.pantalla_chat.config(state=tk.DISABLED)
        self.pantalla_chat.see(tk.END)

    def _enviar_mensaje(self):
        if not self.contacto_seleccionado:
            return
        texto = self.entrada_mensaje.get().strip()
        if not texto:
            return

        remitente = self.usuario_actual.nombre_usuario
        destinatario = self.contacto_seleccionado["username"]

        try:
            self.servicio_mensajeria.enviar_mensaje(remitente, destinatario, texto)
            self.entrada_mensaje.delete(0, tk.END)
            self._actualizar_pantalla_chat()
        except Exception as e:
            messagebox.showerror("Error", str(e))


class PanelProfesor(ttk.Frame):
    def __init__(self, padre, usuario_conectado, servicio_calificacion, servicio_mensajeria):
        super().__init__(padre)
        self.usuario_conectado = usuario_conectado
        self.servicio_calificacion = servicio_calificacion
        self.servicio_mensajeria = servicio_mensajeria
        self.pack(fill=tk.BOTH, expand=True)
        self._configurar_pestanas()

    def _configurar_pestanas(self):
        cuaderno = ttk.Notebook(self)
        cuaderno.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        pestana1 = ttk.Frame(cuaderno)
        cuaderno.add(pestana1, text=f"Materia: {self.usuario_conectado.materia_asignada}")
        tabla1 = VistaTablaCalificaciones(pestana1, self.servicio_calificacion, self.usuario_conectado, self.usuario_conectado.materia_asignada, es_editable=True, es_vista_grupo=False)
        tabla1.pack(fill=tk.BOTH, expand=True)
        tabla1.cargar_datos(self.servicio_calificacion.obtener_calificaciones_materia(self.usuario_conectado.materia_asignada))

        if self.usuario_conectado.puede_ver_calificaciones_grupo():
            pestana2 = ttk.Frame(cuaderno)
            cuaderno.add(pestana2, text="Seguimiento de Grupo (Tutor)")
            tabla2 = VistaTablaCalificaciones(pestana2, self.servicio_calificacion, self.usuario_conectado, self.usuario_conectado.materia_asignada, es_editable=False, es_vista_grupo=True)
            tabla2.pack(fill=tk.BOTH, expand=True)
            tabla2.cargar_datos(self.servicio_calificacion.obtener_calificaciones_grupo(self.usuario_conectado.id_grupo))

        pestana3 = ttk.Frame(cuaderno)
        cuaderno.add(pestana3, text="Mensajería")
        VistaMensajeria(pestana3, self.usuario_conectado, self.servicio_mensajeria).pack(fill=tk.BOTH, expand=True)


class PanelAlumno(ttk.Frame):
    def __init__(self, padre, usuario_conectado, servicio_calificacion, servicio_mensajeria):
        super().__init__(padre)
        self.usuario_conectado = usuario_conectado
        self.servicio_calificacion = servicio_calificacion
        self.servicio_mensajeria = servicio_mensajeria
        self.pack(fill=tk.BOTH, expand=True)
        self._configurar_pestanas()

    def _configurar_pestanas(self):
        cuaderno = ttk.Notebook(self)
        cuaderno.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        pestana1 = ttk.Frame(cuaderno)
        cuaderno.add(pestana1, text="Mis Calificaciones")
        tabla_cal = VistaTablaCalificaciones(pestana1, self.servicio_calificacion, self.usuario_conectado, es_editable=False, es_vista_grupo=False)
        tabla_cal.pack(fill=tk.BOTH, expand=True)
        tabla_cal.cargar_datos(self.servicio_calificacion.obtener_calificaciones_alumno(self.usuario_conectado.nombre_completo))

        pestana2 = ttk.Frame(cuaderno)
        cuaderno.add(pestana2, text="Mensajería con Profesores")
        VistaMensajeria(pestana2, self.usuario_conectado, self.servicio_mensajeria).pack(fill=tk.BOTH, expand=True)


# APLICACIÓN PRINCIPAL 
class VentanaPrincipal(tk.Tk):
    def __init__(self, uri="mongodb+srv://txlito:Irving11@cluster0.ha23c3n.mongodb.net/?appName=Cluster0", db_name="proyecto_completo"):
        super().__init__()
        self.title("Sistema de Gestión Académica - POO + MongoDB Atlas + SOLID")
        self.geometry("950x550")
        self.minsize(800, 480)
        self.configure(bg="#0F172A")

        aplicar_tema_personalizado()

        try:
            self.repositorio = RepositorioMongo()
        except Exception as e:
            messagebox.showerror("Error de Conexión", f"No se pudo conectar a MongoDB Atlas: {str(e)}")
            sys.exit(1)

        self.servicio_autenticacion = ServicioAutenticacion(self.repositorio)
        self.servicio_calificacion = ServicioCalificacion(self.repositorio)
        self.servicio_mensajeria = ServicioMensajeria(self.repositorio, self.repositorio)

        self.mostrar_inicio_sesion()

    def mostrar_inicio_sesion(self):
        self._limpiar_vista()
        VistaInicioSesion(self, self.servicio_autenticacion, self.manejar_exito_inicio_sesion)

    def manejar_exito_inicio_sesion(self, usuario_conectado):
        self._limpiar_vista()
        if isinstance(usuario_conectado, Alumno):
            PanelAlumno(self, usuario_conectado, self.servicio_calificacion, self.servicio_mensajeria)
        else:
            PanelProfesor(self, usuario_conectado, self.servicio_calificacion, self.servicio_mensajeria)

    def _limpiar_vista(self):
        for widget in self.winfo_children():
            widget.destroy()


if __name__ == "__main__":
    app = VentanaPrincipal()
    app.mainloop()
