import cv2
import tkinter as tk
from tkinter import messagebox, scrolledtext
from PIL import Image, ImageTk
from ultralytics import YOLO
import mysql.connector as mysql
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import os
import time
import serial

# Configuración del puerto Serial
conexion = serial.Serial('COM14', 9600)

RUTA_IMAGENES = r"D:\Javier Maldonado - 4\Capitulo 7 - Aprendizaje Supervisado\iconos" 

CATEGORIAS = {
    'bolsas': 'Plástico', 'botellas': 'Plástico',
    'papel': 'Papel', 'carton': 'Papel',
    'manzana': 'Orgánico', 'platano': 'Orgánico', 'naranja': 'Orgánico',
    'latas': 'Metal'
}

COLORES_REPORTES = {
    'Plástico': '#2196F3', 
    'Papel': '#FF9800',    
    'Orgánico': '#4CAF50', 
    'Metal': '#F44336'     
}

COLOR_FONDO_GRIS = '#1e1e1e' 

ejecutando = False
cap = None
modelo = YOLO(r"D:\Javier Maldonado - 4\Capitulo 7 - Aprendizaje Supervisado\runs-hoy\detect\objetos\weights\best.pt")

contador_frames = 0
objeto_candidato = None
tiempos_bloqueo = {'Plástico': 0, 'Papel': 0, 'Metal': 0, 'Orgánico': 0}
ultimo_tiempo_deteccion = time.time()

def escribir_terminal(mensaje):
    terminal.config(state=tk.NORMAL)
    hora_actual = datetime.now().strftime("%H:%M:%S")
    terminal.insert(tk.END, f"[{hora_actual}] {mensaje}\n")
    terminal.see(tk.END)
    terminal.config(state=tk.DISABLED)

def conectar_db():
    try:
        return mysql.connect(
            host="electro-hogar-proyecto-practica-electrohogar13-8038.b.aivencloud.com", 
            user="avnadmin", 
            password="AVNS_Fwf7wKQJzyI6s9iq2cp", 
            database="sistema_residuos",
            port=26873        )
    except Exception as e:
        escribir_terminal(f"Error DB: {e}")
        return None

def registrar_deteccion(etiqueta, conf, cantidad):
    global contador_frames, objeto_candidato, tiempos_bloqueo
    
    actualizar_panel_izquierdo(etiqueta, conf * 100)
    
    if etiqueta == objeto_candidato:
        contador_frames += 1
    else:
        objeto_candidato = etiqueta
        contador_frames = 0
        return

    # Si se confirma el objeto tras 10 frames estables
    if contador_frames == 10:
        cat_general = CATEGORIAS.get(etiqueta, "Otros")
        ahora_unix = time.time()

        # Filtro de tiempo: Solo registrar si pasaron más de 5 segundos
        if ahora_unix - tiempos_bloqueo.get(cat_general, 0) > 5:
            conn = conectar_db()
            if conn:
                # 1. Guardar en Base de Datos
                cursor = conn.cursor()
                query = "INSERT INTO detecciones (clase_especifica, categoria_general, fecha, hora, cantidad) VALUES (%s, %s, %s, %s, %s)"
                valores = (etiqueta, cat_general, datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%H:%M:%S'), cantidad)
                
                cursor.execute(query, valores)
                conn.commit()
                conn.close()
                
                # Actualizar el tiempo de bloqueo para esta categoría
                tiempos_bloqueo[cat_general] = ahora_unix
                escribir_terminal(f"DB REGISTRO: {etiqueta.upper()} -> {cat_general}")

                # 2. ENVIAR AL ARDUINO AL MISMO TIEMPO
                # Se envía solo cuando se confirma el insert exitoso y se respeta el delay de 5s
                if cat_general == 'Plástico':
                    conexion.write(b'0')
                elif cat_general == 'Papel':
                    conexion.write(b'1')
                elif cat_general == 'Metal':
                    conexion.write(b'2')
                elif cat_general == 'Orgánico':
                    conexion.write(b'3')
                else:
                    conexion.write(b'4')
        
        contador_frames = 0
        objeto_candidato = None

def procesar_imagen_con_fondo(img_path, size=(400, 400)):
    if os.path.exists(img_path):
        img_pil = Image.open(img_path).convert("RGBA")
        fondo = Image.new("RGBA", img_pil.size, COLOR_FONDO_GRIS)
        img_final = Image.alpha_composite(fondo, img_pil).convert("RGB")
        img_final = img_final.resize(size, Image.LANCZOS)
        return ImageTk.PhotoImage(img_final)
    return None

def mostrar_imagen_defecto():
    img_path = os.path.join(RUTA_IMAGENES, "signo.png")
    photo = procesar_imagen_con_fondo(img_path)
    if photo:
        canvas_info.image = photo
        canvas_info.create_image(200, 200, image=photo)
    else:
        canvas_info.delete("all")
        canvas_info.create_text(200, 200, text="SISTEMA LISTO", fill="white", font=("Arial", 14, "bold"))

def actualizar_panel_izquierdo(etiqueta, precision):
    # Esta función ahora solo maneja la parte visual de la interfaz de usuario
    lbl_nombre_prod.config(text=f"PRODUCTO: {etiqueta.upper()}")
    lbl_precision_prod.config(text=f"PRECISIÓN: {precision:.2f}%")
    img_path = os.path.join(RUTA_IMAGENES, f"{etiqueta}.png")
    photo = procesar_imagen_con_fondo(img_path)
    if photo:
        canvas_info.image = photo 
        canvas_info.create_image(200, 200, image=photo)

def mostrar_reportes():
    conn = conectar_db()
    if not conn: return
    cursor = conn.cursor()
    cursor.execute("SELECT categoria_general, SUM(cantidad) FROM detecciones GROUP BY categoria_general")
    data = cursor.fetchall()
    conn.close()

    if not data:
        messagebox.showinfo("Reporte", "No hay datos en la base de datos.")
        return

    labels = [d[0] for d in data]
    values = [d[1] for d in data]
    colores_grafico = [COLORES_REPORTES.get(l, '#CCCCCC') for l in labels]

    ventana_stats = tk.Toplevel(ventana)
    ventana_stats.title("Estadísticas de Residuos")
    ventana_stats.configure(bg="#f0f0f0")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.bar(labels, values, color=colores_grafico)
    ax1.set_title("Conteo por Categoría")
    ax2.pie(values, labels=labels, autopct='%1.1f%%', colors=colores_grafico, startangle=140)
    ax2.set_title("Distribución %")

    canvas_grafico = FigureCanvasTkAgg(fig, master=ventana_stats)
    canvas_grafico.draw()
    canvas_grafico.get_tk_widget().pack(padx=10, pady=10)

def actualizar_video():
    global ejecutando, cap, photo_cam, ultimo_tiempo_deteccion, objeto_candidato, contador_frames
    
    if ejecutando:
        ret, frame = cap.read()
        if ret:
            # Redimensionar el frame para la interfaz
            frame = cv2.resize(frame, (540, 400))
            
            # Pasar el frame por el modelo YOLO
            results = modelo(frame, conf=0.6)
            
            # Si hay detecciones, procesarlas
            if len(results[0].boxes) > 0:
                ultimo_tiempo_deteccion = time.time() # <-- Reiniciar el temporizador
                
                conteo_frame = {}
                confianzas_maximas = {}

                for box in results[0].boxes:
                    label = modelo.names[int(box.cls[0])]
                    conf = float(box.conf[0])

                    if label in CATEGORIAS:
                        conteo_frame[label] = conteo_frame.get(label, 0) + 1
                        if conf > confianzas_maximas.get(label, 0.0):
                            confianzas_maximas[label] = conf

                for label, cantidad_detectada in conteo_frame.items():
                    conf_max = confianzas_maximas[label]
                    registrar_deteccion(label, conf_max, cantidad_detectada)
            
            else:
                # --- NUEVA LÓGICA: Si no hay detecciones ---
                if time.time() - ultimo_tiempo_deteccion > 2.0:
                    # Solo actualizamos si no estamos ya en el estado de espera
                    if lbl_nombre_prod.cget("text") != "PRODUCTO: ESPERANDO...":
                        lbl_nombre_prod.config(text="PRODUCTO: ESPERANDO...")
                        lbl_precision_prod.config(text="PRECISIÓN: 0.00%")
                        mostrar_imagen_defecto()
                        # Reiniciamos las variables de validación por seguridad
                        objeto_candidato = None
                        contador_frames = 0

            # Guardamos la imagen procesada con los recuadros de YOLO
            frame_dibujado = results[0].plot()
            
            # Convertir el formato de color de OpenCV (BGR) a Tkinter (RGB)
            img_rgb = cv2.cvtColor(frame_dibujado, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(img_rgb)
            photo_cam = ImageTk.PhotoImage(image=img_pil)
            
            # Limpiar por completo el canvas antes de dibujar para no acumular capas
            canvas_camara.delete("all")
            
            # Dibujar el nuevo frame en las coordenadas del canvas
            canvas_camara.create_image(0, 0, image=photo_cam, anchor=tk.NW)
            
            # Mantener la referencia viva en memoria para que Python no la borre
            canvas_camara.image = photo_cam 
            
        # Ejecutar el siguiente frame en 10ms
        ventana.after(10, actualizar_video)


def iniciar():
    global ejecutando, cap
    if not ejecutando:
        cap = cv2.VideoCapture(0)
        ejecutando = True
        escribir_terminal("Cámara Iniciada")
        actualizar_video()

def detener():
    global ejecutando, cap
    ejecutando = False
    if cap: 
        cap.release()
    
    # Limpiar el canvas por completo y resetear variables de la UI
    canvas_camara.delete("all")
    canvas_camara.image = None  # Liberar la referencia de memoria de la cámara
    
    lbl_nombre_prod.config(text="PRODUCTO: ESPERANDO...")
    lbl_precision_prod.config(text="PRECISIÓN: 0.00%")
    escribir_terminal("Sistema Detenido")
    mostrar_imagen_defecto()

ventana = tk.Tk()
ventana.title("SENATI - Clasificador de Residuos")
ventana.geometry("1250x710")
ventana.configure(bg="#121212")

frame_principal = tk.Frame(ventana, bg="#121212")
frame_principal.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

frame_izquierdo = tk.Frame(frame_principal, bg="#1e1e1e", bd=2, relief=tk.FLAT)
frame_izquierdo.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

tk.Label(frame_izquierdo, text="PRODUCTO", font=("Arial", 16, "bold"), fg="#ffffff", bg="#1e1e1e").pack(pady=20)
canvas_info = tk.Canvas(frame_izquierdo, width=400, height=400, bg=COLOR_FONDO_GRIS, highlightthickness=1, highlightbackground="#333")
canvas_info.pack(pady=10)

lbl_nombre_prod = tk.Label(frame_izquierdo, text="PRODUCTO: ESPERANDO...", font=("Arial", 14), fg="#4CAF50", bg="#1e1e1e")
lbl_nombre_prod.pack(pady=10)
lbl_precision_prod = tk.Label(frame_izquierdo, text="PRECISIÓN: 0.00%", font=("Arial", 14), fg="#4CAF50", bg="#1e1e1e")
lbl_precision_prod.pack()

frame_derecho = tk.Frame(frame_principal, bg="#121212")
frame_derecho.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10)

tk.Label(frame_derecho, text="CÁMARA", font=("Arial", 16, "bold"), fg="#ffffff", bg="#121212").pack(pady=10)
canvas_camara = tk.Canvas(frame_derecho, width=540, height=400, bg="black", highlightthickness=2, highlightbackground="#4CAF50")
canvas_camara.pack(pady=5)

frame_botones = tk.Frame(frame_derecho, bg="#121212")
frame_botones.pack(pady=10)

tk.Button(frame_botones, text="INICIAR", bg="#2e7d32", fg="white", font=("Arial", 10, "bold"), width=12, height=2, command=iniciar).pack(side=tk.LEFT, padx=5)
tk.Button(frame_botones, text="DETENER", bg="#c62828", fg="white", font=("Arial", 10, "bold"), width=12, height=2, command=detener).pack(side=tk.LEFT, padx=5)
tk.Button(frame_botones, text="REPORTES", bg="#1976D2", fg="white", font=("Arial", 10, "bold"), width=12, height=2, command=mostrar_reportes).pack(side=tk.LEFT, padx=5)

tk.Label(frame_derecho, text="HISTORIAL DE ACTIVIDAD", font=("Arial", 9, "bold"), fg="#777", bg="#121212").pack(anchor=tk.W, padx=5)
terminal = scrolledtext.ScrolledText(frame_derecho, height=12, bg="#000", fg="#00ff00", font=("Consolas", 9), state=tk.DISABLED)
terminal.pack(fill=tk.BOTH, expand=True, pady=5)

mostrar_imagen_defecto()
ventana.mainloop()