# Herramienta para Correos Masivos (Antigravity Mail)

Una aplicación web local ultra-premium, moderna e intuitiva diseñada en Python y Vanilla CSS/JS para gestionar y enviar campañas de correos electrónicos masivos y personalizados utilizando protocolos SMTP (como Gmail) mediante listas cargadas desde archivos Excel (`.xlsx`) o `.csv`.

---

## 🚀 Características Clave

* **Diseño Premium Glassmorphism:** Interfaz de usuario de una sola página (SPA) inspirada en tendencias modernas de diseño web con modo oscuro profundo, gradientes vibrantes y transiciones ultra-fluidas.
* **Configuración SMTP Inteligente & Simplificada:** Solo necesitas ingresar tu correo y tu contraseña de aplicación. El sistema detecta automáticamente configuraciones para Gmail y oculta parámetros avanzados bajo un menú desplegable.
* **Vista Previa en Vivo (Live Simulator):** Observa en tiempo real cómo lucirá tu correo letra por letra antes de enviarlo. Traduce dinámicamente el marcador `{{NOMBRE}}` utilizando un destinatario de ejemplo resaltado visualmente.
* **Carga Drag & Drop:** Arrastra tus listas de Excel o CSV de forma interactiva y previsualiza los contactos directamente en una tabla dinámica en pantalla.
* **Seguimiento Visual de Progreso:**
  * **Barra de Progreso Animada:** Visualización fluida que se llena en tiempo real conectada mediante WebSockets al backend.
  * **Contadores de Campaña:** Widgets informativos para Total, Enviados y Fallidos.
  * **Terminal de Logs en Vivo:** Visualiza el registro de conexiones SMTP y estado de cada correo en un panel interactivo (verde para éxito, rojo para errores).
  * **Botón de Detención Inmediata:** Detén la campaña asíncrona de manera segura con un solo clic.
* **Persistencia Local Segura:** Almacena tus credenciales SMTP localmente en una base de datos SQLite ligera para que no tengas que escribirlas de nuevo.
* **Contenedorizado Docker (Optimizado para OrbStack):** Levanta la aplicación con un solo comando, con volumen persistente y libre de conflictos de puertos.

---

## 🛠️ Requisitos Previos

Asegúrate de tener instalados:
* [Docker](https://www.docker.com/) o [OrbStack](https://orbstack.dev/) (Recomendado para macOS).
* O bien, Python 3.9+ instalado en tu máquina si prefieres la ejecución nativa.

---

## 📦 Instrucciones de Inicio Rápido

### Opción A: Usando Docker (Recomendado)

Esta opción aísla por completo la herramienta en un contenedor y mapea el puerto de forma segura a **[http://localhost:8085](http://localhost:8085)**:

1. Clona el repositorio e ingresa al directorio del proyecto.
2. Inicia los servicios con Docker Compose:
   ```bash
   docker compose up -d --build
   ```
3. Abre tu navegador favorito e ingresa a: **[http://localhost:8085](http://localhost:8085)**.
4. Para detener la aplicación:
   ```bash
   docker compose down
   ```

### Opción B: Ejecución Local Nativa (Python)

Si prefieres ejecutar el servidor directamente en tu máquina:

1. Crea e instala las dependencias en un entorno virtual:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Corre el servidor FastAPI en un puerto libre alternativo:
   ```bash
   uvicorn app:app --reload --port 8085
   ```
3. Ingresa en tu navegador a: **[http://localhost:8085](http://localhost:8085)**.

---

## 📊 Formato de Archivos Permitidos (Excel / CSV)

El parser inteligente del backend detecta automáticamente las columnas del archivo subido. Asegúrate de tener al menos las siguientes columnas (mayúsculas o minúsculas no importan):
* **Nombre** (ej. `Juan Pérez`)
* **Correo** o **Email** (ej. `juan.perez@ejemplo.com`)

---

## 🔒 Seguridad SMTP

La aplicación guarda tus credenciales localmente en la base de datos `antigravity_mail.db` dentro de tu propia máquina. Ningún dato sale de tu entorno local hacia servidores externos.

*Para usar Gmail:* Recuerda que debes activar la verificación en dos pasos en tu cuenta de Google y generar una **Contraseña de Aplicación (App Password)** de 16 caracteres. No uses la contraseña habitual de tu correo.
