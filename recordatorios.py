import json
import os
import io
import requests
import pypdf
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

# =============================================
# TUS DATOS
# =============================================
TOKEN   = "8618568769:AAFSOKd82wllh1GMbIyAdSi3Nj98DKCjkWA"
CHAT_ID = 1068023319
HORA_REVISION = "08:00"   # hora en que revisa los PDFs cada día hábil
# =============================================

# Secciones a revisar: (nombre visible, prefijo del archivo, carpeta)
# Agregá o quitá filas según lo que necesites
SECCIONES = [
    ("Cámara 1ra Civil Sec. A",  "CC1A",  "cc1a"),
    ("Cámara 1ra Civil Sec. B",  "CC1B",  "cc1b"),
    ("Cámara 2da Civil Sec. A",  "CC2A",  "cc2a"),
    ("Cámara 2da Civil Sec. B",  "CC2B",  "cc2b"),
    ("Cámara 4ta Civil Sec. A",  "CC4A",  "cc4a"),
    ("Cámara 4ta Civil Sec. B",  "CC4B",  "cc4b"),
]

BASE_URL        = "https://justicialarioja.gob.ar/despachos"
ARCHIVO_NOMBRES = "nombres.json"

# Estado conversación
ESPERANDO_NOMBRE = 0

# ── Helpers de persistencia ──────────────────────────────────────────────────

def cargar_nombres() -> list:
    if os.path.exists(ARCHIVO_NOMBRES):
        with open(ARCHIVO_NOMBRES, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def guardar_nombres(nombres: list):
    with open(ARCHIVO_NOMBRES, "w", encoding="utf-8") as f:
        json.dump(nombres, f, ensure_ascii=False, indent=2)

# ── Lógica de descarga y búsqueda ────────────────────────────────────────────

def construir_urls(fecha: datetime):
    dd    = fecha.strftime("%d")
    mm    = fecha.strftime("%m")
    yy    = fecha.strftime("%y")
    sufijo = f"{dd}{mm}{yy}"
    urls = []
    for nombre, prefijo, carpeta in SECCIONES:
        url_normal = f"{BASE_URL}/{carpeta}/{prefijo}-{sufijo}.pdf"
        url_comp   = f"{BASE_URL}/{carpeta}/{prefijo}-{sufijo}-COMPLEMENTARIA.pdf"
        urls.append((nombre, url_normal, url_comp))
    return urls

def extraer_texto_pdf(url: str):
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        reader = pypdf.PdfReader(io.BytesIO(resp.content))
        texto = "\n".join(p.extract_text() or "" for p in reader.pages)
        return texto
    except Exception:
        return None

def buscar_nombres_en_texto(texto: str, nombres: list) -> list:
    texto_lower = texto.lower()
    return [n for n in nombres if n.lower() in texto_lower]

# ── Tarea diaria ─────────────────────────────────────────────────────────────

async def revisar_despachos(context: ContextTypes.DEFAULT_TYPE):
    hoy = datetime.today()
    if hoy.weekday() >= 5:
        return

    nombres = cargar_nombres()
    if not nombres:
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text="ℹ️ No tenés nombres para buscar. Usá /agregar para añadir uno."
        )
        return

    urls_del_dia = construir_urls(hoy)
    algun_pdf = False

    for nombre_seccion, url_normal, url_comp in urls_del_dia:
        for url, es_comp in [(url_normal, False), (url_comp, True)]:
            texto = extraer_texto_pdf(url)
            if texto is None:
                continue

            algun_pdf = True
            encontrados = buscar_nombres_en_texto(texto, nombres)
            tipo = " (COMPLEMENTARIA)" if es_comp else ""

            if encontrados:
                lista = "\n".join(f"  • {n}" for n in encontrados)
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=(
                        f"🔔 *Coincidencias encontradas*\n\n"
                        f"📄 *{nombre_seccion}{tipo}*\n"
                        f"📅 {hoy.strftime('%d/%m/%Y')}\n\n"
                        f"Nombres encontrados:\n{lista}\n\n"
                        f"🔗 [Ver PDF]({url})"
                    ),
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=(
                        f"✅ *{nombre_seccion}{tipo}* — {hoy.strftime('%d/%m/%Y')}\n"
                        f"Ningún nombre de tu lista aparece en el despacho de hoy."
                    ),
                    parse_mode="Markdown"
                )

    if not algun_pdf:
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=f"📭 No se encontraron despachos publicados para hoy ({hoy.strftime('%d/%m/%Y')})."
        )

# ── Búsqueda manual ───────────────────────────────────────────────────────────

async def buscar_ahora(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Buscando en los despachos de hoy, esperá un momento...")
    await revisar_despachos(context)

# ── Comandos ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "👋 ¡Hola! Soy tu bot de despachos judiciales.\n\n"
        "Cada día hábil reviso los PDFs del Poder Judicial de La Rioja "
        "y te aviso si aparece algún nombre de tu lista.\n\n"
        "📌 *Comandos:*\n"
        "/agregar — Agregar un nombre a buscar\n"
        "/listar — Ver los nombres que seguís\n"
        "/borrar — Eliminar un nombre de la lista\n"
        "/buscar — Revisar los despachos de hoy ahora mismo\n"
        "/ayuda — Ver esta ayuda"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombres = cargar_nombres()
    if not nombres:
        await update.message.reply_text("📭 No tenés nombres guardados.\nUsá /agregar para añadir uno.")
        return
    lista = "\n".join(f"{i+1}. {n}" for i, n in enumerate(nombres))
    await update.message.reply_text(f"📋 *Nombres que seguís:*\n\n{lista}", parse_mode="Markdown")

async def agregar_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✏️ Escribí el nombre o apellido que querés buscar.\n\n"
        "Ejemplo: `García` o `García Juan Carlos`\n\nO /cancelar para salir.",
        parse_mode="Markdown"
    )
    return ESPERANDO_NOMBRE

async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre = update.message.text.strip()
    nombres = cargar_nombres()
    if nombre.lower() in [n.lower() for n in nombres]:
        await update.message.reply_text("⚠️ Ese nombre ya está en tu lista.")
        return ConversationHandler.END
    nombres.append(nombre)
    guardar_nombres(nombres)
    await update.message.reply_text(f"✅ *{nombre}* agregado a tu lista.", parse_mode="Markdown")
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END

async def borrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombres = cargar_nombres()
    if not nombres:
        await update.message.reply_text("📭 No tenés nombres para borrar.")
        return
    lista = "\n".join(f"{i+1}. {n}" for i, n in enumerate(nombres))
    await update.message.reply_text(f"🗑 ¿Cuál querés borrar? Escribí el número:\n\n{lista}", parse_mode="Markdown")
    context.user_data["esperando_borrar"] = True

async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("esperando_borrar"):
        context.user_data["esperando_borrar"] = False
        nombres = cargar_nombres()
        try:
            idx = int(update.message.text.strip()) - 1
            if 0 <= idx < len(nombres):
                eliminado = nombres.pop(idx)
                guardar_nombres(nombres)
                await update.message.reply_text(f"✅ *{eliminado}* eliminado.", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Número inválido.")
        except ValueError:
            await update.message.reply_text("❌ Escribí solo el número.")
    else:
        await update.message.reply_text("No entendí ese mensaje. Usá /ayuda para ver los comandos.")

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("agregar", agregar_inicio)],
        states={ESPERANDO_NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)]},
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("ayuda",  ayuda))
    app.add_handler(CommandHandler("listar", listar))
    app.add_handler(CommandHandler("borrar", borrar))
    app.add_handler(CommandHandler("buscar", buscar_ahora))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))

    app.job_queue.run_daily(
        revisar_despachos,
        time=datetime.strptime(HORA_REVISION, "%H:%M").time()
    )

    print(f"✅ Bot iniciado. Revisará despachos todos los días hábiles a las {HORA_REVISION}.")
    app.run_polling()

if __name__ == "__main__":
    main()
