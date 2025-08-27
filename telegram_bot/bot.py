import os
import sys
import django
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import logging
from asgiref.sync import sync_to_async

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'feria_inmobiliaria.settings')
django.setup()

from sales.models import Sale

# Configuración
BOT_TOKEN = os.getenv("BOT_TOKEN", "8487994847:AAGtHOTrU3gPplzODE3QxHn0TsdjZCgJBk8")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "5882977799"))

EMPRESAS = ["InmoPlus", "VentaMax", "CasaFácil", "TopCasa", "PropiedadPro"]
DISTRITOS = ["Miraflores", "San Isidro", "La Molina", "Surco", "Barranco", "Chorrillos"]
TIPOS = ["Apartamento", "Casa", "Local comercial", "Oficina", "Terreno", "Bodega"]

# Estado temporal por usuario (wizard /ventarapida)
user_sale_data = {}  # {user_id: {"empresa":..., "asesor":..., "tipo":..., "distrito":..., "precio":..., "comision":..., "stage":...}}

class FeriaBot:
    def __init__(self):
        self.app = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()

    def setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("ventas", self.ventas_command))
        self.app.add_handler(CommandHandler("ranking", self.ranking_command))
        self.app.add_handler(CommandHandler("venta", self.nueva_venta_command))

        # NUEVO: flujo guiado
        self.app.add_handler(CommandHandler("ventarapida", self.venta_rapida_command))

        # (opcionales que ya tenías)
        self.app.add_handler(CommandHandler("empresa", self.empresa_command))
        self.app.add_handler(CommandHandler("zona", self.zona_command))
        self.app.add_handler(CommandHandler("asesor", self.asesor_command))
        self.app.add_handler(CommandHandler("help", self.help_command))

        # Callbacks de botones y entrada de texto
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_input))

    # ---------- Comandos base ----------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Bienvenido al Bot de Feria Inmobiliaria!\n\n"
            "Comandos disponibles:\n"
            "/ventas - Ver estadísticas\n"
            "/ranking - Ver ranking de asesores\n"
            "/venta - Registrar nueva venta (solo admin)\n"
            "/ventarapida - Registrar venta guiada (solo admin)"
        )

    async def ventas_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            total_sales = await sync_to_async(Sale.objects.count)()
            sales_list = await sync_to_async(list)(Sale.objects.all())
            total_amount = sum(float(s.price) for s in sales_list)

            msg = "📊 ESTADÍSTICAS\n\n"
            msg += f"🏠 Total ventas: {total_sales}\n"
            msg += f"💰 Volumen total: ${total_amount:,.0f}\n"
            msg += f"📈 Promedio: ${total_amount/total_sales:,.0f}" if total_sales else "📈 Promedio: $0"
            await update.message.reply_text(msg)
        except Exception as e:
            logger.exception("ventas_command")
            await update.message.reply_text(f"❌ Error: {e}")

    async def ranking_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            sales_list = await sync_to_async(list)(Sale.objects.all())
            sales_by_agent = {}
            for sale in sales_list:
                d = sales_by_agent.setdefault(sale.agent_name, {"count": 0, "total": 0.0, "company": sale.company})
                d["count"] += 1
                d["total"] += float(sale.price)

            if not sales_by_agent:
                await update.message.reply_text("📊 No hay ventas registradas aún.")
                return

            sorted_agents = sorted(sales_by_agent.items(), key=lambda x: x[1]["count"], reverse=True)
            msg = "🏆 RANKING DE ASESORES\n\n"
            for i, (agent, data) in enumerate(sorted_agents[:10], 1):
                emoji = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}."))
                msg += f"{emoji} {agent} ({data['company']})\n"
                msg += f"   {data['count']} ventas - ${data['total']:,.0f}\n\n"
            await update.message.reply_text(msg)
        except Exception as e:
            logger.exception("ranking_command")
            await update.message.reply_text(f"❌ Error: {e}")

    async def nueva_venta_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != SUPER_ADMIN_ID:
            await update.message.reply_text("❌ Solo el administrador puede registrar ventas")
            return

        if not context.args:
            await update.message.reply_text(
                "Formato: /venta nombre,empresa,tipo,ubicación,precio,comisión\n\n"
                "Ejemplo:\n/venta María García,InmoPlus,Apartamento,Miraflores,180000,9000"
            )
            return

        try:
            data = ' '.join(context.args).split(',')
            if len(data) < 5:
                raise ValueError("Faltan datos")

            sale = await sync_to_async(Sale.objects.create)(
                agent_name=data[0].strip(),
                company=data[1].strip(),
                property_type=data[2].strip(),
                location=data[3].strip(),
                price=float(data[4].strip()),
                commission=float(data[5].strip()) if len(data) > 5 else 0,
                client_name="Cliente registrado via bot"
            )

            await update.message.reply_text(
                "✅ VENTA REGISTRADA\n\n"
                f"👤 {sale.agent_name} ({sale.company})\n"
                f"🏠 {sale.property_type} en {sale.location}\n"
                f"💰 ${float(sale.price):,.0f}\n"
                f"💸 Comisión: ${float(sale.commission):,.0f}"
            )
        except Exception as e:
            logger.exception("nueva_venta_command")
            await update.message.reply_text(f"❌ Error: {e}")

    # ---------- NUEVO: /ventarapida (flujo guiado con botones) ----------
    async def venta_rapida_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != SUPER_ADMIN_ID:
            await update.message.reply_text("❌ Solo el administrador puede registrar ventas")
            return

        user_sale_data[user_id] = {"stage": "empresa"}
        keyboard = [[InlineKeyboardButton(empresa, callback_data=f"empresa_{empresa}")] for empresa in EMPRESAS]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🏢 Selecciona la empresa:", reply_markup=reply_markup)

    async def get_asesores_by_empresa(self, empresa: str):
        # Devuelve lista única de asesores para esa empresa (ordenados)
        asesores = await sync_to_async(
            lambda: sorted(
                set(Sale.objects.filter(company=empresa).values_list("agent_name", flat=True))
            )
        )()
        return asesores

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data
        if user_id not in user_sale_data:
            user_sale_data[user_id] = {}

        # Empresa seleccionada
        if data.startswith("empresa_"):
            empresa = data.replace("empresa_", "")
            user_sale_data[user_id]["empresa"] = empresa
            user_sale_data[user_id]["stage"] = "asesor"

            asesores = await self.get_asesores_by_empresa(empresa)
            keyboard = [[InlineKeyboardButton(a, callback_data=f"asesor_{a}")] for a in asesores] if asesores else []
            keyboard.append([InlineKeyboardButton("➕ Nuevo asesor", callback_data="nuevo_asesor")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"Empresa: {empresa}\n\n👤 Selecciona el asesor:",
                reply_markup=reply_markup
            )

        # Crear nuevo asesor (entrada por texto)
        elif data == "nuevo_asesor":
            user_sale_data[user_id]["stage"] = "nuevo_asesor_nombre"
            await query.edit_message_text(
                f"Empresa: {user_sale_data[user_id].get('empresa','')}\n\n✍️ Escribe el *nombre del asesor*:",
                parse_mode="Markdown"
            )

        # Asesor seleccionado
        elif data.startswith("asesor_"):
            asesor = data.replace("asesor_", "")
            user_sale_data[user_id]["asesor"] = asesor
            user_sale_data[user_id]["stage"] = "tipo"

            keyboard = [[InlineKeyboardButton(t, callback_data=f"tipo_{t}")] for t in TIPOS]
            await query.edit_message_text(
                f"Empresa: {user_sale_data[user_id]['empresa']}\nAsesor: {asesor}\n\n🏠 Selecciona *tipo de propiedad*:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        # Tipo de propiedad
        elif data.startswith("tipo_"):
            tipo = data.replace("tipo_", "")
            user_sale_data[user_id]["tipo"] = tipo
            user_sale_data[user_id]["stage"] = "distrito"

            keyboard = [[InlineKeyboardButton(d, callback_data=f"distrito_{d}")] for d in DISTRITOS]
            await query.edit_message_text(
                "Empresa: {empresa}\nAsesor: {asesor}\nTipo: {tipo}\n\n📍 Selecciona *distrito*:".format(
                    empresa=user_sale_data[user_id]['empresa'],
                    asesor=user_sale_data[user_id]['asesor'],
                    tipo=tipo
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        # Distrito
        elif data.startswith("distrito_"):
            distrito = data.replace("distrito_", "")
            user_sale_data[user_id]["distrito"] = distrito
            user_sale_data[user_id]["stage"] = "precio"

            await query.edit_message_text(
                "Empresa: {empresa}\nAsesor: {asesor}\nTipo: {tipo}\nDistrito: {d}\n\n💰 Ingresa el *precio* (solo número, sin comas):".format(
                    empresa=user_sale_data[user_id]['empresa'],
                    asesor=user_sale_data[user_id]['asesor'],
                    tipo=user_sale_data[user_id]['tipo'],
                    d=distrito
                ),
                parse_mode="Markdown"
            )

        # Confirmación (guardar) o cancelar
        elif data == "confirmar_guardar":
            try:
                sale = await sync_to_async(Sale.objects.create)(
                    agent_name=user_sale_data[user_id]["asesor"],
                    company=user_sale_data[user_id]["empresa"],
                    property_type=user_sale_data[user_id]["tipo"],
                    location=user_sale_data[user_id]["distrito"],
                    price=float(user_sale_data[user_id]["precio"]),
                    commission=float(user_sale_data[user_id]["comision"]),
                    client_name="Cliente registrado via bot"
                )
                await query.edit_message_text(
                    "✅ VENTA REGISTRADA\n\n"
                    f"👤 {sale.agent_name} ({sale.company})\n"
                    f"🏠 {sale.property_type} en {sale.location}\n"
                    f"💰 ${float(sale.price):,.0f}\n"
                    f"💸 Comisión: ${float(sale.commission):,.0f}"
                )
            except Exception as e:
                logger.exception("confirmar_guardar")
                await query.edit_message_text(f"❌ Error al guardar: {e}")
            finally:
                user_sale_data.pop(user_id, None)

        elif data == "cancelar_venta":
            user_sale_data.pop(user_id, None)
            await query.edit_message_text("❌ Registro cancelado.")

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recoge entradas de texto durante el wizard: nuevo asesor, precio y comisión."""
        user_id = update.effective_user.id
        if user_id != SUPER_ADMIN_ID:
            return  # ignorar textos de no-admin para el wizard

        if user_id not in user_sale_data or "stage" not in user_sale_data[user_id]:
            return  # no está en wizard

        stage = user_sale_data[user_id]["stage"]
        text = (update.message.text or "").strip()

        # 1) Nombre de nuevo asesor
        if stage == "nuevo_asesor_nombre":
            if len(text) < 2:
                await update.message.reply_text("⚠️ Nombre muy corto. Intenta nuevamente:")
                return
            user_sale_data[user_id]["asesor"] = text
            user_sale_data[user_id]["stage"] = "tipo"

            keyboard = [[InlineKeyboardButton(t, callback_data=f"tipo_{t}")] for t in TIPOS]
            await update.message.reply_text(
                f"Empresa: {user_sale_data[user_id]['empresa']}\nAsesor: {text}\n\n🏠 Selecciona *tipo de propiedad*:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # 2) Precio (número)
        if stage == "precio":
            try:
                precio = float(text.replace(",", "").replace(" ", ""))
                if precio <= 0:
                    raise ValueError
                user_sale_data[user_id]["precio"] = precio
                user_sale_data[user_id]["stage"] = "comision"
                await update.message.reply_text("💸 Ingresa la *comisión* (solo número, sin comas):", parse_mode="Markdown")
            except Exception:
                await update.message.reply_text("⚠️ Precio inválido. Escribe solo números (ej: 180000).")
            return

        # 3) Comisión (número) → mostrar confirmación
        if stage == "comision":
            try:
                comision = float(text.replace(",", "").replace(" ", ""))
                if comision < 0:
                    raise ValueError
                user_sale_data[user_id]["comision"] = comision
                user_sale_data[user_id]["stage"] = "confirmar"

                d = user_sale_data[user_id]
                resumen = (
                    "🧾 *CONFIRMAR VENTA*\n\n"
                    f"🏢 Empresa: {d['empresa']}\n"
                    f"👤 Asesor: {d['asesor']}\n"
                    f"🏠 Tipo: {d['tipo']}\n"
                    f"📍 Distrito: {d['distrito']}\n"
                    f"💰 Precio: ${d['precio']:,.0f}\n"
                    f"💸 Comisión: ${d['comision']:,.0f}\n\n"
                    "¿Deseas guardar?"
                )
                keyboard = [
                    [InlineKeyboardButton("✅ Guardar", callback_data="confirmar_guardar")],
                    [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_venta")]
                ]
                await update.message.reply_text(resumen, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception:
                await update.message.reply_text("⚠️ Comisión inválida. Escribe solo números (ej: 9000).")
            return

    # ---------- Placeholders para tus otros comandos (si los usas) ----------
    async def empresa_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Usa /ventarapida para seleccionar empresa con botones.")

    async def zona_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Usa /ventarapida para seleccionar distrito con botones.")

    async def asesor_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Usa /ventarapida para seleccionar asesor con botones.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "/start, /ventas, /ranking, /venta, /ventarapida\n"
            "Sigue el flujo de /ventarapida para registrar ventas con botones."
        )

    # ---------- Run ----------
    def run(self):
        print("Bot iniciado...")
        self.app.run_polling()

if __name__ == "__main__":
    bot = FeriaBot()
    bot.run()
