// Diccionario español → inglés de la interfaz (v5.8). El español es la «llave»: se traduce solo cuando el texto coincide EXACTO.
// Cómo ampliarlo: abre la app en inglés, escribe `i18nFaltantes()` en la consola del navegador y agrega aquí lo que salga.
// Reglas: una línea por texto; la traducción conserva los signos («¿…?» → «…?») y no lleva comillas dobles dentro.

// ---------- Menú, roles y estructura general ----------
const ESTRUCTURA = {
  "Administrador": "Administrator", "Residente": "Resident", "Guardia": "Security guard", "Inquilino": "Tenant",
  "Inicio": "Home", "Reservas": "Reservations", "Mis paquetes": "My packages", "Paquetes": "Packages", "Mis pagos": "My payments",
  "Pagos del apartamento": "Apartment payments", "Cartera": "Accounts receivable", "Votaciones": "Votes", "Asambleas": "Assemblies",
  "Mis visitas": "My visitors", "Visitas": "Visitors", "Arrendamientos": "Leases", "Mis inquilinos": "My tenants", "Trasteos": "Moves",
  "Portería": "Front desk", "Reportar un daño": "Report damage", "Daños": "Damage reports", "Quejas y sugerencias": "Complaints and suggestions",
  "PQRS": "Requests & complaints", "Cartelera": "Notice board", "Comercio": "Local shops", "Documentos": "Documents", "Emergencias": "Emergencies",
  "Indicadores": "Indicators", "Cargar datos": "Import data", "Auditoría": "Audit log", "Usuarios": "Users", "Ajustes": "Settings", "Más": "More", "Pagos": "Payments",
  "Esperando conexión con el servidor": "Waiting for the server connection",
  "Tu sesión sigue abierta. Si el servidor estaba dormido puede tardar hasta un minuto en despertar; lo intentamos de nuevo solo.": "You are still signed in. If the server was asleep it can take up to a minute to wake up; we will keep trying automatically.",
  "Reintentar ahora": "Retry now", "Reintentar": "Retry",
  "Activa los avisos en Ajustes para enterarte de paquetes y votaciones aunque la app esté cerrada.": "Turn on notifications in Settings to hear about packages and votes even when the app is closed.",
  "Hay registros sin enviar": "Some records have not been sent", "Cerrar sesión": "Sign out", "Mi cuenta": "My account", "Abrir menú de mi cuenta": "Open my account menu",
  "Principal": "Main", "Sin conexión. Lo que registres se guarda en este equipo y se envía solo.": "No connection. Whatever you record is saved on this device and sent automatically.",
  "Enviar ahora": "Send now", "Registros que el servidor no aceptó": "Records the server did not accept",
  "Se hicieron sin internet, pero al enviarlos el servidor los rechazó (por ejemplo, porque otra persona ya lo había registrado). No se repiten solos.": "They were made offline, but the server rejected them when sent (for example, because someone else had already recorded it). They are not retried automatically.",
  "Entendido": "Got it", "No pudimos cargar esta sección": "We could not load this section", "Tu sesión expiró. Ingresa de nuevo.": "Your session expired. Please sign in again.",
  "Cerrar": "Close", "Confirmar": "Confirm", "Volver": "Back", "Cancelar": "Cancel", "Guardar": "Save", "Aceptar": "OK", "Enviar": "Send", "Editar": "Edit", "Eliminar": "Delete",
  "Buscar": "Search", "Todos": "All", "Todas": "All", "Sí": "Yes", "No": "No", "Ver": "View", "Ver todos": "View all", "Ver todas": "View all", "Nuevo": "New", "Nueva": "New",
  "Tema claro": "Light theme", "Tema oscuro": "Dark theme", "Cambiar tema": "Change theme", "Cargando…": "Loading…", "Cargando": "Loading", "Sin datos": "No data",
  "ahora mismo": "just now", "Estado": "Status", "Fecha": "Date", "Acciones": "Actions", "Nombre": "Name", "Detalle": "Details", "Descripción": "Description", "Título": "Title",
  "Teléfono": "Phone", "Apartamento": "Apartment", "Apto": "Apt", "Total": "Total", "Saldo": "Balance", "Cuota": "Fee", "Zona": "Area", "Tipo": "Type", "Asunto": "Subject",
  "Pendiente": "Pending", "Aprobada": "Approved", "Aprobado": "Approved", "Rechazada": "Rejected", "Rechazado": "Rejected", "Cancelada": "Cancelled", "Cancelado": "Cancelled",
  "Abierto": "Open", "Abierta": "Open", "Solucionado": "Solved", "Por aprobar": "To approve", "En Revision": "Under review", "En revisión": "Under review",
  "En Reparacion": "Being repaired", "En reparación": "Being repaired", "En porteria": "At the front desk", "En portería": "At the front desk", "Radicada": "Filed",
  "En tramite": "In progress", "En trámite": "In progress", "Resuelta": "Resolved", "Cerrada": "Closed", "Anulado": "Voided", "Anulada": "Voided", "Entregado": "Delivered",
  "Al día": "Up to date", "En mora": "Overdue", "Pendiente de pago": "Payment pending", "Activa": "Active", "Activo": "Active", "Vencida": "Expired", "Vencido": "Expired",
  "Revocado": "Revoked", "Usado": "Used", "Dentro": "Inside", "Finalizado": "Finished", "Convocada": "Called", "En sesión": "In session", "Borrador": "Draft",
  "En curso": "In progress", "Completado": "Completed", "Vigente": "Valid", "No vigente": "Not valid", "Reunión": "Meeting", "Evento": "Event", "Aviso": "Notice",
  "Urgente": "Urgent", "Mantenimiento": "Maintenance", "Reportado": "Reported", "Solucionados": "Solved", "Aprobados": "Approved", "Abiertos": "Open", "En proceso": "In progress",
};

// ---------- Ingreso ----------
const LOGIN = {
  "Mostrar contraseña": "Show password", "Ocultar contraseña": "Hide password", "Ingresar": "Sign in", "Código de verificación": "Verification code",
  "Abre tu app de autenticación y escribe el código de 6 dígitos. ¿Perdiste el celular? Usa uno de tus códigos de recuperación.": "Open your authenticator app and enter the 6-digit code. Lost your phone? Use one of your recovery codes.",
  "Escribe tu correo y tu contraseña.": "Enter your email and password.", "Bienvenido de nuevo": "Welcome back",
  "Ingresa con la cuenta que te creó la administración.": "Sign in with the account the administration created for you.",
  "Correo electrónico": "Email", "Contraseña": "Password",
  "¿Olvidaste tu contraseña o aún no tienes cuenta? Pídela en la administración de tu conjunto.": "Forgot your password or do not have an account yet? Ask your complex administration.",
  "Reservas, mantenimiento, cartera y portería en un solo lugar, para administradores, residentes y guardias.": "Reservations, maintenance, accounts and front desk in one place, for administrators, residents and security guards.",
  "Control residencial inteligente": "Smart residential management",
};

// ---------- Notificaciones (campana, tarjeta de Inicio y avisos que genera el servidor) ----------
const NOTIFICACIONES = {
  "Notificaciones": "Notifications", "Por gestionar": "To handle", "Gestionadas": "Handled", "Gestionada": "Handled", "Filtrar avisos": "Filter notices",
  "Marcar como gestionada": "Mark as handled", "Volver a pendiente": "Back to pending", "Nada por gestionar": "Nothing to handle",
  "Estás al día. Aquí aparecerán los avisos que esperan una acción tuya.": "You are all caught up. Notices waiting for your action will appear here.",
  "Aún no hay avisos gestionados": "No handled notices yet", "Cuando gestiones un aviso (o se resuelva solo), lo verás aquí.": "When you handle a notice (or it resolves itself), you will see it here.",
  "Sin notificaciones": "No notifications", "Aquí verás avisos de paquetes, PQRS, reservas, anuncios y documentos.": "Here you will see notices about packages, requests, reservations, announcements and documents.",
  "Marcar todas como leídas": "Mark all as read", "Avisos por gestionar": "Notices to handle", "Tienes 1 aviso por gestionar": "You have 1 notice to handle", "Tienes avisos por gestionar": "You have notices to handle",
  "Reserva por aprobar": "Reservation to approve", "Nuevo daño por atender": "New damage report to attend", "Daño por aprobar: el técnico terminó": "Damage report to approve: the technician is done",
  "El técnico actualizó un daño": "The technician updated a damage report", "Nueva queja o sugerencia": "New complaint or suggestion", "Tu reporte fue aprobado y cerrado": "Your report was approved and closed",
  "Tu reporte volvió a atención": "Your report is being handled again", "Tu reporte quedó solucionado": "Your report has been solved", "Tienes un paquete en portería": "You have a package at the front desk",
  "Tu poder fue aprobado": "Your proxy was approved", "Tu poder no fue aprobado": "Your proxy was not approved",
};

// ---------- Inicio (Resumen) ----------
const RESUMEN = {
  "Bienvenido a tu conjunto.": "Welcome to your complex.", "Todo al día": "All caught up", "No hay reservas esperando aprobación.": "No reservations waiting for approval.",
  "Reserva aprobada": "Reservation approved", "Aprobar": "Approve", "Así va tu conjunto hoy.": "Here is how your complex is doing today.", "Por atender hoy": "To handle today",
  "Reservas, daños, PQRS, anuncios y arrendamientos": "Reservations, damage reports, requests, announcements and leases", "Reservas por aprobar": "Reservations to approve",
  "Daños sin resolver": "Unresolved damage reports", "Daños por aprobar": "Damage reports to approve", "Apartamentos en mora": "Apartments overdue", "Vehículos dentro": "Vehicles inside",
  "Anuncios por revisar": "Announcements to review", "Paquetes sin entregar": "Undelivered packages", "Arrendamientos por aprobar": "Leases to approve", "PQRS por atender": "Requests to attend",
  "Residentes activos": "Active residents", "Daños recientes": "Recent damage reports", "Gestionar": "Manage", "Sin daños pendientes": "No pending damage reports", "Todo está solucionado.": "Everything is solved.",
  "Tu voto es secreto y toma un minuto.": "Your vote is secret and takes a minute.", "Saldo de administración": "Maintenance fee balance", "Estás al día": "You are up to date",
  "En mora · reservas bloqueadas": "Overdue · reservations blocked", "Ver mi cuenta": "View my account", "Pagar ahora": "Pay now", "Accesos rápidos": "Quick links",
  "Reservar una zona común": "Reserve a common area", "Avisar que viene una visita": "Announce a visitor", "Reglamento y documentos": "Rules and documents", "Teléfonos de emergencia": "Emergency phone numbers",
  "Comercio del conjunto": "Complex shops", "Mis próximas reservas": "My upcoming reservations", "Sin reservas próximas": "No upcoming reservations", "Reserva el salón, la zona BBQ y más.": "Reserve the hall, the BBQ area and more.",
  "Mis reportes": "My reports", "Sin reportes": "No reports", "Cuando reportes un daño verás su avance aquí.": "When you report damage, you will see its progress here.", "Mi arrendamiento": "My lease",
  "Mi apartamento": "My apartment", "Pagar la administración del apartamento": "Pay the apartment maintenance fee", "Reglamento y circulares": "Rules and circulars", "Resumen del turno.": "Shift summary.",
  "Ir a portería y escanear": "Go to the front desk and scan", "Visitantes a pie dentro": "Pedestrian visitors inside", "Reservas aprobadas hoy": "Reservations approved today", "En el parqueadero": "In the parking lot",
  "Portería despejada": "Front desk clear", "No hay visitantes dentro.": "No visitors inside.", "Reservas de hoy": "Today's reservations", "Sin eventos hoy": "No events today", "No hay zonas comunes reservadas para hoy.": "No common areas reserved for today.",
  "No se pudo completar el registro.": "The record could not be completed.", "Sin conexión: quedó guardado en este equipo y se enviará solo al volver internet.": "Offline: saved on this device and will be sent automatically when the internet returns.",
};

// ---------- Daños (Mantenimiento) ----------
const DANIOS = {
  "Ampliar foto": "Enlarge photo", "Foto de evidencia del técnico": "Technician evidence photo", "Ampliar foto de evidencia": "Enlarge evidence photo", "Técnico": "Technician",
  "¿Aprobar este reporte?": "Approve this report?", "Aprobar y cerrar": "Approve and close", "Reporte aprobado y cerrado.": "Report approved and closed.",
  "Reporte devuelto. Crea un enlace nuevo para que se atienda de nuevo.": "Report sent back. Create a new link so it can be handled again.", "Devolver el reporte": "Send the report back", "Devolver": "Send back",
  "El reporte vuelve a «Abierto» y le avisamos al residente. Después puedes crear un enlace nuevo para que el técnico lo atienda otra vez.": "The report goes back to “Open” and we notify the resident. Then you can create a new link so the technician can handle it again.",
  "¿Qué hay que corregir? (opcional, lo verá el residente)": "What needs to be fixed? (optional, the resident will see it)",
  "1 día": "1 day", "3 días (recomendado)": "3 days (recommended)", "7 días (el máximo)": "7 days (the maximum)", "Enlace copiado.": "Link copied.",
  "No se pudo copiar: selecciona el enlace y cópialo a mano.": "Could not copy: select the link and copy it by hand.", "Copiar": "Copy", "Enviar por WhatsApp": "Send by WhatsApp", "Anular": "Void",
  "Todavía no has creado enlaces para este reporte.": "You have not created any links for this report yet.", "No se pudo cargar la lista de enlaces.": "Could not load the list of links.",
  "¿Anular este enlace?": "Void this link?", "El técnico ya no podrá abrirlo ni actualizar el reporte. Cuando quieras puedes crear otro.": "The technician will no longer be able to open it or update the report. You can create another one whenever you want.",
  "Anular enlace": "Void link", "Enlace anulado.": "Link voided.", "Enlace listo. Cualquiera que lo tenga puede abrirlo hasta que venza o lo anules.": "Link ready. Anyone who has it can open it until it expires or you void it.",
  "Enlace para el técnico": "Link for the technician", "Enlace creado. Si había otro vigente, quedó anulado.": "Link created. If there was another valid one, it was voided.", "Generar enlace": "Create link",
  "El técnico lo abre sin contraseña. Podrá pasar el reporte a «En reparación» o «Solucionado» y subir su foto de evidencia con una nota. Cuando lo marque como solucionado, tú revisas la evidencia y lo apruebas. Cada cambio queda en la auditoría y le avisa al residente.": "The technician opens it without a password. They can move the report to “Being repaired” or “Solved” and upload an evidence photo with a note. When they mark it as solved, you review the evidence and approve it. Every change is recorded in the audit log and notifies the resident.",
  "Esto es lo que verá el técnico (más la foto del daño):": "This is what the technician will see (plus the damage photo):",
  "Nunca verá el nombre ni el teléfono de quien reportó, pero el texto se muestra tal cual: revisa que no incluya datos personales.": "They will never see the name or phone of who reported it, but the text is shown as written: check that it does not include personal data.",
  "¿Cuánto tiempo sirve el enlace?": "How long is the link valid?", "¿Para quién es? (opcional, solo lo ves tú)": "Who is it for? (optional, only you see it)", "Enlaces de este reporte": "Links for this report",
  "Sin foto": "No photo", "Avance del reporte": "Report progress", "Revisión final": "Final review", "El técnico terminó. Revisa su nota y su foto y decide:": "The technician is done. Review their note and photo and decide:",
  "El técnico ya terminó. La administración hará la revisión final.": "The technician is done. The administration will do the final review.",
  "El técnico ya terminó: aprueba o devuelve el reporte": "The technician is done: approve or send back the report", "Este reporte ya está aprobado": "This report is already approved",
  "Crear un enlace temporal para que un técnico lo atienda sin cuenta": "Create a temporary link so a technician can handle it without an account", "Enlace para técnico": "Technician link",
  "No hay reportes en esta categoría.": "There are no reports in this category.", "Agregar foto del daño (opcional)": "Add a photo of the damage (optional)",
  "Toma la foto con la cámara o elígela de tu galería": "Take the photo with the camera or pick it from your gallery", "Enviar reporte": "Send report",
  "El título debe tener al menos 5 caracteres.": "The title must be at least 5 characters long.", "Describe el daño con al menos 10 caracteres.": "Describe the damage with at least 10 characters.",
  "Reporte enviado. ¡Gracias por avisar!": "Report sent. Thanks for letting us know!", "¿Qué pasó?": "What happened?", "Cuéntanos los detalles": "Tell us the details",
  "Borrador cargado. Revisa lo que escribió la IA, agrega una foto si quieres y envíalo.": "Draft loaded. Review what the AI wrote, add a photo if you like and send it.",
  "Borrador cargado. Revísalo, agrega una foto si quieres y envíalo.": "Draft loaded. Review it, add a photo if you like and send it.",
  "El técnico atiende cada reporte desde su enlace. Tú revisas su evidencia y apruebas al final.": "The technician handles each report from their link. You review their evidence and approve at the end.",
  "Cuéntanos qué se dañó en las zonas comunes y sigue cómo avanza la solución.": "Tell us what got damaged in the common areas and follow how the solution progresses.",
};

// ---------- Chat y asistente de IA ----------
const CHAT = {
  "¿Qué residentes están en mora?": "Which residents are overdue?", "¿Qué tengo pendiente por gestionar?": "What do I have pending to handle?", "¿Cómo apruebo una reserva?": "How do I approve a reservation?",
  "¿Qué zonas están más congestionadas?": "Which areas are the busiest?", "¿Cómo registro un pago de administración?": "How do I record a maintenance fee payment?",
  "¿Cómo publico un aviso en la Cartelera?": "How do I post a notice on the notice board?", "¿Cómo reservo una zona?": "How do I reserve an area?", "¿Cómo creo un pase QR para una visita?": "How do I create a QR pass for a visitor?",
  "¿Qué puedo hacer como inquilino?": "What can I do as a tenant?", "¿Qué eventos hay próximamente?": "What events are coming up?", "¿Qué día está más libre la Zona BBQ?": "Which day is the BBQ area most free?",
  "¿Hay votaciones abiertas?": "Are there any open votes?", "¿Cómo registro el ingreso de un vehículo?": "How do I record a vehicle entry?", "¿Cómo valido el PIN de un pase?": "How do I validate a pass PIN?",
  "¿Cómo registro un paquete?": "How do I record a package?", "¿Qué hago si no hay internet?": "What do I do if there is no internet?",
  "Reservas por día": "Reservations per day", "No hay nada por mostrar.": "There is nothing to show.", "Preguntas sugeridas": "Suggested questions", "Ayuda de portería": "Front desk help", "Datos reales de reservas": "Real reservation data",
  "Parece que no tienes internet. Cuando vuelva la conexión, inténtalo de nuevo.": "You seem to be offline. When the connection is back, try again.", "No pude responder ahora. Inténtalo de nuevo en un momento.": "I could not answer right now. Please try again in a moment.",
  "Intentar de nuevo": "Try again", "Escribe tu pregunta…": "Type your question…", "Enviar mensaje": "Send message", "Nueva conversación": "New conversation", "Cerrar chat": "Close chat",
  "Residentes en mora": "Overdue residents", "Reservas pendientes": "Pending reservations", "Quejas y sugerencias abiertas": "Open complaints and suggestions", "Daños sin cerrar": "Open damage reports", "Daños por aprobar": "Damage reports to approve",
  "Trasteos por aprobar": "Moves to approve", "Arrendamientos por aprobar": "Leases to approve", "Paquetes sin recoger": "Uncollected packages", "Abrir Cartera": "Open Accounts receivable", "Aprobar reservas": "Approve reservations",
  "Abrir Quejas y sugerencias": "Open Complaints and suggestions", "Abrir Mantenimiento": "Open Maintenance", "Ver Trasteos": "View Moves", "Ver Arrendamientos": "View Leases", "Ver paquetes": "View packages",
  "Residente ": "Resident ", "Remitente": "Sender", "Llegó": "Arrived", "Radicada ": "Filed ", "Reportado ": "Reported ", "Desde": "From", "Hasta": "Until", "Empresa": "Company", "Quién": "Who", "Aviso ": "Notice ",
  "No escribas cédulas, teléfonos ni contraseñas. Tu texto se envía a un servicio de IA externo solo para redactar el borrador.": "Do not write ID numbers, phone numbers or passwords. Your text is sent to an external AI service only to write the draft.",
  "Petición": "Request", "Queja": "Complaint", "Reclamo": "Claim", "Sugerencia": "Suggestion", "Ya usaste todas tus consultas de hoy.": "You have used all of today's queries.", "Ayúdame a redactarlo": "Help me write it",
  "Preparar borrador": "Prepare draft", "Asistente de IA": "AI assistant", "Cuéntame un poco más (mínimo 10 caracteres).": "Tell me a bit more (at least 10 characters).",
  "Cuéntame con tus palabras qué pasó. Preparo un borrador y tú lo revisas y lo envías.": "Tell me in your own words what happened. I will prepare a draft and you review and send it.",
  "¿Qué pasó o qué necesitas?": "What happened or what do you need?", "Ver teléfonos de emergencia": "View emergency phone numbers", "Borrador cargado. Revísalo y envíalo cuando estés de acuerdo.": "Draft loaded. Review it and send it when you agree.",
  "Daño en zona común": "Damage in a common area", "Esto parece una petición o queja, así que te llevo al formulario de solicitudes.": "This looks like a request or complaint, so I will take you to the requests form.",
  "Esto parece un daño en una zona común, así que te llevo al formulario de daños.": "This looks like damage in a common area, so I will take you to the damage form.",
  "Es un borrador hecho por IA: puede tener errores. Nada se envía hasta que lo envíes tú.": "This is an AI-made draft: it may contain mistakes. Nothing is sent until you send it.",
  "Usar este borrador": "Use this draft", "Llevar este borrador al formulario": "Take this draft to the form", "Generar borrador": "Generate draft", "Describe el aviso con un poco más de detalle.": "Describe the notice in a little more detail.",
  "Redactar con IA": "Write with AI", "Cuéntame qué debe saber la comunidad (qué, cuándo y dónde). La IA llena el formulario con un borrador; tú lo revisas y decides si publicar.": "Tell me what the community should know (what, when and where). The AI fills in the form with a draft; you review it and decide whether to publish.",
  "Describe el aviso": "Describe the notice",
};

// ---------- Reservas ----------
const RESERVAS = {
  "Salón Comunal": "Community Hall", "Salon Comunal": "Community Hall", "Hasta 60 personas": "Up to 60 people", "Zona BBQ": "BBQ Area", "Hasta 20 personas": "Up to 20 people", "Piscina": "Swimming pool", "Uso por turnos": "Use by shifts",
  "Gimnasio": "Gym", "Clases y eventos": "Classes and events", "Cancha múltiple": "Multi-sport court", "Fútbol y baloncesto": "Soccer and basketball", "Sala de juegos": "Game room", "Hasta 15 personas": "Up to 15 people",
  "¿Cancelar esta reserva?": "Cancel this reservation?", "Sí, cancelar": "Yes, cancel", "Reserva cancelada": "Reservation cancelled", "Sin reservas aquí": "No reservations here", "Cuando solicites una zona común aparecerá en esta lista.": "When you request a common area it will appear in this list.",
  "No hay reservas con este filtro.": "There are no reservations with this filter.", "Pendientes": "Pending", "Aprobadas": "Approved", "Canceladas": "Cancelled", "Toca un día libre en el calendario.": "Tap a free day on the calendar.",
  "Zona común": "Common area", "Solicitar reserva": "Request reservation", "Toca en el calendario el día que quieres.": "Tap the day you want on the calendar.", "Solicitud enviada. La administración la revisará.": "Request sent. The administration will review it.",
  "Nueva reserva": "New reservation", "Tu apartamento registra saldo en mora. ": "Your apartment has an overdue balance. ", "Ponte al día": "Get up to date", " para volver a reservar.": " to reserve again.",
  "1. ¿Qué zona quieres?": "1. Which area do you want?", "2. ¿Qué día?": "2. Which day?", "3. ¿A qué hora?": "3. What time?", "Hora de inicio": "Start time", "Todas las reservas": "All reservations", "Mis reservas": "My reservations",
  "Aprueba o cancela las solicitudes de zonas comunes.": "Approve or cancel common area requests.", "Consulta quién tiene reservada cada zona común para validar a quien llega.": "Check who has reserved each common area to validate who arrives.",
  "Reserva las zonas comunes de tu conjunto en segundos.": "Reserve your complex's common areas in seconds.",
};

// ---------- Quejas y sugerencias (PQRS) ----------
const PQRS = {
  "Peticion": "Request", "Solicitas algo a la administración.": "You are asking the administration for something.", "Algo no funcionó bien o te molesta.": "Something did not work well or bothers you.",
  "Hay un cobro o servicio que no estás de acuerdo.": "There is a charge or service you disagree with.", "Tienes una idea para mejorar.": "You have an idea to improve things.", "En trámite (aún trabajando en ello)": "In progress (still working on it)",
  "Resuelta (ya tiene respuesta)": "Resolved (already answered)", "Escribe la respuesta para el residente.": "Write the reply for the resident.", "Solicitud actualizada. El residente fue avisado.": "Request updated. The resident was notified.",
  "Respuesta para el residente": "Reply for the resident", "Por atender": "To attend", "Abiertas": "Open", "Resueltas": "Resolved", "Editar respuesta": "Edit reply", "Responder": "Reply", "Sin solicitudes en esta vista": "No requests in this view",
  "Aún no has enviado solicitudes": "You have not sent any requests yet", "Cuando un residente radique una PQRS aparecerá aquí.": "When a resident files a request it will appear here.",
  "Usa el formulario para enviar una petición, queja, reclamo o sugerencia.": "Use the form to send a request, complaint, claim or suggestion.", "Tipo de solicitud": "Type of request", "Enviar solicitud": "Send request",
  "Escribe un asunto de al menos 5 caracteres.": "Write a subject of at least 5 characters.", "Cuéntanos un poco más (mínimo 10 caracteres).": "Tell us a bit more (at least 10 characters).", "Nueva solicitud": "New request",
  "Cuéntanos qué pasó o qué necesitas": "Tell us what happened or what you need", "PQRS exportadas a Excel.": "Requests exported to Excel.", "Exportar a Excel": "Export to Excel",
  "Peticiones, quejas, reclamos y sugerencias de los residentes.": "Requests, complaints, claims and suggestions from residents.",
  "Cuéntale a la administración lo que necesitas, lo que no te gustó o tus ideas, y sigue su respuesta.": "Tell the administration what you need, what you did not like or your ideas, and follow their reply.",
  "Solicitudes": "Requests", "Mis solicitudes": "My requests",
};

// ---------- Cartera y pagos ----------
const CARTERA = {
  "Enlace de verificación copiado.": "Verification link copied.", "No se pudo copiar el enlace.": "Could not copy the link.", "Comprobante": "Receipt", "Cómo pagar": "How to pay",
  "Paga por transferencia y avisa en la administración.": "Pay by bank transfer and let the administration know.", "Cuando la administración registre tu pago, aparece aquí abajo con su comprobante en PDF.": "When the administration records your payment, it appears below with its PDF receipt.",
  "Generar y descargar": "Generate and download", "Paz y salvo": "Clearance certificate", "¿Para qué lo necesitas? (opcional)": "What do you need it for? (optional)",
  "Certificado en PDF para mudanzas o trámites bancarios. Lleva un código QR: quien lo reciba lo escanea y comprueba en línea que es auténtico y está vigente.": "PDF certificate for moves or bank procedures. It carries a QR code: whoever receives it scans it and checks online that it is authentic and valid.",
  "Para generar el paz y salvo el apartamento debe estar al día con la administración.": "To generate the clearance certificate the apartment must be up to date with the administration.",
  "Copiar el enlace de verificación": "Copy the verification link", "Enlace": "Link", "Pagar administración": "Pay maintenance fee", "Valor a pagar (COP)": "Amount to pay (COP)", "La mitad": "Half",
  "Modo de pruebas: eliges PSE, tarjeta o Nequi, pero no se cobra dinero real.": "Test mode: you choose PSE, card or Nequi, but no real money is charged.",
  "Estás al día con la administración. Puedes reservar zonas comunes sin restricciones.": "You are up to date with the administration. You can reserve common areas without restrictions.", "Reservar una zona": "Reserve an area",
  "Estado de cuenta": "Account statement", "Descárgalo en PDF para tus trámites. Si estás al día, indica que el apartamento está a paz y salvo.": "Download it as a PDF for your paperwork. If you are up to date, it states that the apartment is cleared.",
  "Descargar PDF": "Download PDF", "Quedaste al día": "You are now up to date", "Aún no has hecho pagos aquí": "You have not made any payments here yet", "Cuando pagues, cada pago queda guardado con su comprobante en PDF.": "When you pay, each payment is saved with its PDF receipt.",
  "Ingresa un valor válido.": "Enter a valid amount.", "Mira cuánto debes, paga la administración y descarga tus comprobantes.": "See how much you owe, pay the maintenance fee and download your receipts.",
  "Cartera total": "Total receivables", "Recaudo mensual esperado": "Expected monthly collection", "Sin apartamento": "No apartment", "Registrar pago": "Record payment", "Generar el paz y salvo con QR": "Generate the clearance certificate with QR",
  "Registrar saldo": "Record balance", "Estado de cuenta en PDF": "Account statement PDF", "Valor recibido (COP)": "Amount received (COP)", "Referencia del comprobante (opcional)": "Receipt reference (optional)",
  "Ingresa un valor igual o mayor a 0.": "Enter an amount equal to or greater than 0.", "Apartamento al día.": "Apartment up to date.", "Saldo registrado. Queda en mora.": "Balance recorded. The apartment is now overdue.",
  "Si el saldo es mayor a 0 el apartamento queda en mora y no podrá reservar zonas comunes.": "If the balance is greater than 0 the apartment becomes overdue and cannot reserve common areas.", "Saldo pendiente (COP)": "Outstanding balance (COP)",
  "Cartera exportada a Excel.": "Accounts exported to Excel.", "Seguimiento del recaudo de administración por apartamento.": "Maintenance fee collection tracking by apartment.", "Cargar desde Excel": "Import from Excel",
  "Aún no hay residentes": "There are no residents yet", "Crea residentes desde la sección Usuarios.": "Create residents from the Users section.", "Estado de cartera": "Account status",
};

// ---------- Paquetes ----------
const PAQUETES = {
  "Paquete": "Package", "Correspondencia": "Mail", "Domicilio": "Delivery", "Ver foto del paquete": "View package photo", "Foto del paquete": "Package photo", "Confirmar entrega": "Confirm delivery",
  "Entregar paquete": "Hand over package", "Entrega registrada": "Delivery recorded", "¿Quién lo recoge?": "Who is picking it up?", "Esperándote en portería": "Waiting for you at the front desk", "En portería sin entregar": "At the front desk, undelivered",
  "Entregados": "Delivered", "Guardado en este equipo; se enviará al volver el internet": "Saved on this device; it will be sent when the internet returns", "Entregar": "Hand over", "¿Anular este registro?": "Void this record?",
  "Úsalo solo si lo registraste por error (por ejemplo, apartamento equivocado). Queda en la auditoría.": "Use it only if you recorded it by mistake (for example, wrong apartment). It stays in the audit log.", "Sí, anular": "Yes, void",
  "Registro anulado": "Record voided", "Nada por recoger": "Nothing to collect", "Portería sin pendientes": "Front desk with nothing pending", "Sin registros": "No records", "Cuando llegue un paquete o una carta para ti, lo verás aquí.": "When a package or letter arrives for you, you will see it here.",
  "No hay paquetes con este filtro.": "There are no packages with this filter.", "Destinatario": "Recipient", "No hay residentes con ese nombre o apartamento.": "There are no residents with that name or apartment.",
  "Foto del paquete (opcional)": "Package photo (optional)", "Sirve de evidencia de cómo llegó": "Serves as evidence of how it arrived", "Registrar llegada": "Record arrival", "Elige a quién va dirigido.": "Choose who it is addressed to.",
  "Buscar residente o apartamento": "Search resident or apartment", "Empresa o mensajero (opcional)": "Company or courier (optional)", "Descripción (opcional)": "Description (optional)", "Ej. «Caja mediana, frágil»": "E.g. “Medium box, fragile”",
  "Buscar por remitente": "Search by sender", "Buscar residente, apartamento o remitente": "Search resident, apartment or sender", "Mira si tienes algo esperándote en portería y cuándo lo recogiste.": "See if something is waiting for you at the front desk and when you collected it.",
  "Registra lo que llega a portería y entrégalo dejando constancia.": "Record what arrives at the front desk and hand it over leaving a record.", "Paquetes y correspondencia": "Packages and mail", "Paquetes exportados a Excel.": "Packages exported to Excel.", "Excel": "Excel",
};

// ---------- Cartelera (anuncios) ----------
const ANUNCIOS = {
  "Reunion": "Meeting", "Ver todo": "View all", "Fijado": "Pinned", "Sin anuncios": "No announcements", "Aquí verás reuniones, eventos y avisos del conjunto.": "Here you will see meetings, events and notices from the complex.",
  "Guardar cambios": "Save changes", "Publicar": "Publish", "Editar anuncio": "Edit announcement", "Nuevo anuncio": "New announcement", "El título debe tener al menos 3 caracteres.": "The title must be at least 3 characters long.",
  "Escribe el mensaje del anuncio.": "Write the announcement message.", "Anuncio actualizado": "Announcement updated", "Anuncio publicado para todos los usuarios": "Announcement published for all users", "Mensaje": "Message",
  "Fecha y hora (si es un evento)": "Date and time (if it is an event)", "Fijar arriba de la cartelera": "Pin to the top of the notice board", "Aún nadie confirmó": "No one has confirmed yet", "Cuando los residentes confirmen aparecerán aquí.": "When residents confirm they will appear here.",
  "Asistiré": "I will attend", "Confirmar asistencia": "Confirm attendance", "Asistentes": "Attendees", "Quitar de fijados": "Unpin", "Fijar arriba": "Pin to top", "¿Eliminar este anuncio?": "Delete this announcement?", "Sí, eliminar": "Yes, delete",
  "Anuncio eliminado": "Announcement deleted", "Reuniones y eventos": "Meetings and events", "Avisos": "Notices", "No hay anuncios": "No announcements", "Publica el primero con el botón «Nuevo anuncio».": "Publish the first one with the “New announcement” button.",
  "Cuando la administración publique algo, lo verás aquí.": "When the administration publishes something, you will see it here.", "Reuniones, eventos y avisos de tu conjunto, siempre al día.": "Meetings, events and notices from your complex, always up to date.",
};

// ---------- Visitas y visitantes ----------
const VISITAS = {
  "Autorizar para hoy": "Authorize for today", "Visita de hoy": "Today's visitor", "Ya está dentro": "Already inside", "Visita cancelada": "Visit cancelled", "Quitar": "Remove", "Sin visitas para hoy": "No visitors for today",
  "Cuando autorices a alguien, aparecerá aquí.": "When you authorize someone, they will appear here.", "Escribe el nombre de tu visita.": "Write your visitor's name.", "Escribe la cédula de tu visita (mínimo 5 números).": "Write your visitor's ID number (at least 5 digits).",
  "Amigo": "Friend", "Listo. Portería ya puede dejarlo pasar hoy.": "Done. The front desk can let them in today.", "¿Quién viene hoy?": "Who is coming today?",
  "Funciona solo por hoy y se vence sola a la medianoche. Pídele a tu visita que lleve su cédula.": "It works for today only and expires by itself at midnight. Ask your visitor to bring their ID.",
  "Nombre de tu visita": "Your visitor's name", "Cédula": "ID number", "Autorizadas para hoy": "Authorized for today", "Hoy": "Today", "Frecuentes": "Frequent", "Vehículo": "Vehicle", "Mi carnet": "My ID card", "Mis visitas": "My visitors",
  "¿Va a llegar alguien? Autorízalo aquí para que portería lo deje pasar.": "Is someone coming? Authorize them here so the front desk lets them in.",
  "Familiar": "Family member", "Servicio domestico": "Domestic service", "Servicio doméstico": "Domestic service", "Cuidador": "Caregiver", "Contratista": "Contractor", "Otro": "Other", "Autorizar": "Authorize",
  "Editar visitante": "Edit visitor", "Autorizar un visitante": "Authorize a visitor", "Escribe el nombre completo.": "Write the full name.", "El documento debe tener entre 5 y 15 letras o números.": "The document must have between 5 and 15 letters or numbers.",
  "Visitante actualizado": "Visitor updated", "Visitante autorizado. Portería ya puede verificarlo.": "Visitor authorized. The front desk can now verify them.", "Nombre completo": "Full name", "Documento (cédula o pasaporte)": "Document (ID or passport)",
  "El documento no se puede cambiar.": "The document cannot be changed.", "Portería lo usa para verificar a la persona.": "The front desk uses it to verify the person.", "Relación": "Relationship", "Autorizado hasta (opcional)": "Authorized until (optional)",
  "Nota para portería (opcional)": "Note for the front desk (optional)", "Ej. «Viene martes y jueves por la mañana»": "E.g. “Comes Tuesdays and Thursdays in the morning”", "Sin vencimiento": "No expiry", " · Aún no ha ingresado": " · Has not entered yet",
  "Dentro del conjunto": "Inside the complex", "¿Retirar la autorización?": "Remove the authorization?", "Sí, retirar": "Yes, remove", "Autorización retirada": "Authorization removed", "Retirar": "Remove", "Sin coincidencias": "No matches",
  "Aún no tienes visitantes autorizados": "You have no authorized visitors yet", "Prueba con otro nombre o documento.": "Try another name or document.",
  "Agrega a tu familia, empleada o cuidador para que portería los deje pasar sin llamarte.": "Add your family, domestic worker or caregiver so the front desk lets them in without calling you.",
  "Buscar por nombre o documento": "Search by name or document", "Visitantes": "Visitors", "Personas autorizadas por los residentes del conjunto.": "People authorized by the complex's residents.",
  "Deja autorizadas a las personas que te visitan seguido: portería las verifica por su documento.": "Pre-authorize the people who visit you often: the front desk verifies them by their document.", "Autorizar visitante": "Authorize visitor",
};

// ---------- Portería ----------
const PORTERIA = {
  "Vehículos dentro": "Vehicles inside", "Registrar salida": "Record exit", "Prueba con otra placa o apartamento.": "Try another plate or apartment.", "No hay visitantes dentro del conjunto.": "There are no visitors inside the complex.",
  "Carro: ABC123 · Moto: ABC12D": "Car: ABC123 · Motorcycle: ABC12D", "Placa": "License plate", "Registrar ingreso": "Record entry", "La placa no tiene un formato válido.": "The license plate does not have a valid format.",
  "Indica el apartamento de destino.": "Enter the destination apartment.", "Apartamento de destino": "Destination apartment", "Buscar placa o apartamento": "Search plate or apartment", "Vehículos": "Vehicles", "Visitantes a pie": "Pedestrian visitors",
  "Escanear QR": "Scan QR", "Historial": "History", "Registra la entrada y salida de vehículos, escanea QR y consulta el historial completo.": "Record vehicle entries and exits, scan QR codes and check the full history.",
};

// ---------- Ajustes ----------
const AJUSTES = {
  "Instalar": "Install", "Instalada ✓": "Installed ✓", "Instalar la app": "Install the app", "Ya la tienes instalada en este dispositivo.": "You already have it installed on this device.",
  "Ábrela desde tu pantalla principal, como cualquier app.": "Open it from your home screen, like any app.", "Avisos activados en este dispositivo.": "Notifications turned on for this device.", "Activar avisos": "Turn on notifications",
  "Te enviamos un aviso de prueba.": "We sent you a test notification.", "Probar": "Test", "Avisos desactivados en este dispositivo.": "Notifications turned off for this device.", "Desactivar": "Turn off", "Avisos en el celular": "Phone notifications",
  "Guarda tus códigos de recuperación": "Save your recovery codes", "Si pierdes el celular, cada uno de estos códigos te deja entrar UNA vez. Se muestran solo ahora: guárdalos en un lugar seguro (no en este mismo celular).": "If you lose your phone, each of these codes lets you in ONCE. They are shown only now: keep them somewhere safe (not on this same phone).",
  "Descargar": "Download", "Códigos copiados.": "Codes copied.", "No se pudo copiar: descárgalos.": "Could not copy: download them.", "Ya los guardé": "I have saved them", "Tu contraseña": "Your password",
  "Vas a vincular una app de autenticación (Google Authenticator, Microsoft Authenticator, Authy…). Primero confirma tu contraseña.": "You are going to link an authenticator app (Google Authenticator, Microsoft Authenticator, Authy…). First confirm your password.",
  "Continuar": "Continue", "Activar la verificación en dos pasos": "Turn on two-step verification", "Código de 6 dígitos": "6-digit code", "1. Abre tu app de autenticación y escanea este código QR.": "1. Open your authenticator app and scan this QR code.",
  "Código QR para la app de autenticación": "QR code for the authenticator app", "2. Escribe el código de 6 dígitos que muestra la app para confirmar.": "2. Enter the 6-digit code shown by the app to confirm.", "Activar": "Turn on",
  "Código de la app o de recuperación": "App or recovery code", "Generar códigos de recuperación nuevos": "Generate new recovery codes", "Generar": "Generate", "Códigos nuevos": "New codes",
  "Desactivar la verificación en dos pasos": "Turn off two-step verification", "Verificación en dos pasos desactivada.": "Two-step verification turned off.",
  "La administración del conjunto exige la verificación en dos pasos. Actívala ahora para proteger la cuenta.": "The complex administration requires two-step verification. Turn it on now to protect the account.",
  "Recomendado para administradores: aunque alguien se entere de tu contraseña, no podrá entrar sin el código de tu celular.": "Recommended for administrators: even if someone learns your password, they cannot sign in without the code from your phone.",
  "Verificación en dos pasos": "Two-step verification", "Dispositivo": "Device", " · este dispositivo": " · this device", "Sesión cerrada.": "Session closed.", "¿Cerrar las demás sesiones?": "Sign out of all other sessions?",
  "Se cierra tu cuenta en todos los demás dispositivos. Este sigue abierto.": "Your account is signed out on all other devices. This one stays open.", "Sí, cerrar": "Yes, sign out", "Cerrar todas las demás": "Sign out of all others",
  "Dispositivos con tu sesión": "Devices with your session", "Si ves uno que no reconoces, ciérralo y cambia tu contraseña.": "If you see one you do not recognize, close it and change your password.", "Configuración": "Settings",
  "Tu perfil y cómo quieres ver la aplicación en este dispositivo.": "Your profile and how you want to see the app on this device.", "Correo": "Email", "Parqueadero": "Parking", "Ninguno": "None", "Sin asignar": "Unassigned",
  "Apariencia": "Appearance", "Tema": "Theme", "Elige entre el modo claro o el oscuro.": "Choose between light and dark mode.", "Claro": "Light", "Oscuro": "Dark", "Fondo ilustrado": "Illustrated background",
  "La ilustración del conjunto detrás del contenido.": "The complex illustration behind the content.", "Animaciones": "Animations", "Transiciones y movimientos suaves. Desactívalas si prefieres una interfaz más quieta.": "Smooth transitions and movement. Turn them off if you prefer a calmer interface.",
  "Tamaño del texto": "Text size", "Hazlo más grande para leer con más comodidad.": "Make it larger to read more comfortably.", "Normal": "Normal", "Grande": "Large", "Sesión y datos": "Session and data",
  "Cámbiala si la compartiste o sospechas que otra persona la conoce.": "Change it if you shared it or suspect someone else knows it.", "Cambiar contraseña": "Change password", "Restablecer apariencia": "Reset appearance",
  "Vuelve al tema claro y a los valores originales.": "Go back to the light theme and the original values.", "Apariencia restablecida": "Appearance reset", "Restablecer": "Reset", "Sales de este dispositivo; tus datos siguen guardados.": "You sign out of this device; your data stays saved.",
  "Idioma": "Language",
};

// ---------- Textos con partes variables (nombres, números, valores). Se aplican sobre el texto ya recortado ----------
// ---------- Documentos, emergencias, usuarios ----------
const GESTION_1 = {
  "Reglamento": "Rules", "Acta": "Minutes", "Circular": "Circular", "Financiero": "Financial", "Otros": "Other", "Subir": "Upload", "Subir documento": "Upload document", "Escribe un título.": "Write a title.",
  "Elige un archivo PDF.": "Choose a PDF file.", "Solo se aceptan archivos PDF.": "Only PDF files are accepted.", "Documento publicado. Todos los usuarios fueron avisados.": "Document published. All users were notified.", "Categoría": "Category",
  "¿Eliminar el documento?": "Delete the document?", "Documento eliminado": "Document deleted", "Aún no hay documentos": "No documents yet", "Sube el reglamento, las actas y las circulares para que todos los consulten.": "Upload the rules, minutes and circulars so everyone can read them.",
  "La administración publicará aquí el reglamento, las actas y las circulares.": "The administration will publish the rules, minutes and circulars here.", "Buscar documento": "Search document", "Reglamento, actas y circulares del conjunto en PDF.": "The complex's rules, minutes and circulars as PDF.",
  "Salud": "Health", "Seguridad": "Security", "Servicios publicos": "Utilities", "Servicios públicos": "Utilities", "Administracion": "Administration", "Administración": "Administration", "Agregar": "Add", "Editar contacto": "Edit contact",
  "Nuevo contacto de emergencia": "New emergency contact", "Escribe el nombre del contacto.": "Write the contact name.", "Escribe un teléfono válido.": "Write a valid phone number.", "Contacto actualizado": "Contact updated", "Contacto agregado": "Contact added", "Orden": "Order",
  "¿Eliminar este contacto?": "Delete this contact?", "Contacto eliminado": "Contact deleted", "Sin contactos": "No contacts", "Agrega la clínica más cercana, el CAI del cuadrante o el servicio de gas.": "Add the nearest clinic, the local police post or the gas service.",
  "La administración aún no ha cargado contactos.": "The administration has not loaded any contacts yet.", "Toca un número para llamar. En una emergencia real, marca primero la línea única 123.": "Tap a number to call. In a real emergency, dial the single emergency line 123 first.",
  "Agrega los números locales de tu conjunto: clínica, CAI del cuadrante, gas, ascensores.": "Add your complex's local numbers: clinic, local police post, gas, elevators.", "Nuevo contacto": "New contact",
  "Residentes": "Residents", "Inquilinos": "Tenants", "Guardias": "Security guards", "Administradores": "Administrators", "Usuario activado": "User turned on", "Usuario desactivado": "User turned off", "Rol": "Role", "Coeficiente": "Coefficient",
  "Asignar": "Assign", "Genera una contraseña temporal": "Generate a temporary password", "Restablecer clave": "Reset password", "Sin resultados": "No results", "Prueba con otro nombre o filtro.": "Try another name or filter.",
  "¿Restablecer la contraseña?": "Reset the password?", "Sí, restablecer": "Yes, reset", "Clave copiada": "Password copied", "Contraseña temporal": "Temporary password", "Clave temporal": "Temporary password",
  "Solo se muestra ahora. Si la pierdes, vuelve a restablecerla.": "It is shown only now. If you lose it, reset it again.", "Solo se muestra ahora. Si se pierde, restablécela desde Usuarios.": "It is shown only now. If it gets lost, reset it from Users.",
  "Listo": "Done", "Parqueadero asignado": "Parking assigned", "Escribe un porcentaje entre 0 y 100, por ejemplo 0,8523.": "Write a percentage between 0 and 100, for example 0.8523.", "Coeficiente quitado": "Coefficient removed", "Coeficiente guardado": "Coefficient saved",
  "Es el porcentaje de copropiedad del apartamento según el reglamento. Entre todos los apartamentos deben sumar 100. Déjalo vacío para quitarlo.": "It is the apartment's co-ownership percentage according to the rules. All apartments must add up to 100. Leave it empty to remove it.",
  "Crear usuario": "Create user", "Nuevo usuario": "New user", "El correo no es válido.": "The email is not valid.", "La contraseña debe tener al menos 8 caracteres.": "The password must be at least 8 characters long.", "Contraseña inicial": "Initial password",
  "Buscar por nombre, correo o apto.": "Search by name, email or apt.", "Buscar usuarios": "Search users", "Crea cuentas, asigna parqueaderos y activa o desactiva accesos.": "Create accounts, assign parking spaces and turn access on or off.", "Usuario": "User",
};

// ---------- Arrendamientos (inquilinos) ----------
const GESTION_2 = {
  "Clave copiada": "Password copied", "Inquilino aprobado": "Tenant approved", "¿Rechazar este arrendamiento?": "Reject this lease?", "Sí, rechazar": "Yes, reject", "¿Cancelar el registro?": "Cancel the registration?", "¿Terminar el arrendamiento?": "End the lease?",
  "Sí, terminar": "Yes, end it", "Arrendamiento rechazado": "Lease rejected", "Listo, el acceso quedó cerrado.": "Done, the access was closed.", "Rechazar": "Reject", "Terminar": "End", "Sin apto.": "No apt.", "Permiso activado": "Permission turned on", "Permiso quitado": "Permission removed",
  "Pagar la administración": "Pay the maintenance fee", "Ve la cartera del apartamento y paga en tu nombre.": "See the apartment's account and pay on your behalf.", "Votar en las asambleas": "Vote in assemblies",
  "Vota por el apartamento. Solo hay un voto: si vota él, ya no votas tú en esa consulta.": "Votes for the apartment. There is only one vote: if they vote, you no longer vote in that poll.", "Activos": "Active", "Vigentes": "Current", "Nada por aquí": "Nothing here",
  "Sin inquilinos": "No tenants", "No hay arrendamientos en esta vista.": "There are no leases in this view.", "Si arriendas tu apartamento, registra aquí a tu inquilino.": "If you rent out your apartment, register your tenant here.", "Enviar para aprobación": "Send for approval",
  "Registrar inquilino": "Register tenant", "Indica desde y hasta cuándo es el contrato.": "Enter the contract start and end dates.", "La fecha de fin debe ser posterior a la de inicio.": "The end date must be after the start date.",
  "Enviado. La administración debe aprobarlo antes de que pueda ingresar.": "Sent. The administration must approve it before they can sign in.", "Nombre completo del inquilino": "Tenant's full name", "Inicio del contrato": "Contract start", "Fin del contrato": "Contract end",
  "Aprueba los contratos que registran los propietarios.": "Approve the contracts that owners register.", "Registra a quien vive en tu apartamento por arrendamiento.": "Register who lives in your apartment as a tenant.",
};

// ---------- Trasteos (mudanzas) ----------
const GESTION_3 = {
  "Salida": "Move out", "Tipo de trasteo": "Type of move", "Voy a sacar muebles": "I am taking furniture out", "Entrada": "Move in", "Voy a meter muebles": "I am bringing furniture in",
  "Para meter muebles solo necesitas la aprobación de la administración.": "To bring furniture in you only need the administration's approval.", "Solicitar un trasteo": "Request a move", "Indica desde y hasta qué hora.": "Enter the start and end times.",
  "La hora final debe ser posterior a la de inicio.": "The end time must be after the start time.", "Solicitud enviada. Te avisamos cuando la administración la revise.": "Request sent. We will let you know when the administration reviews it.", "¿Qué vas a hacer?": "What are you going to do?",
  "Máximo 12 horas por solicitud. La portería solo deja pasar el trasteo dentro de este horario.": "Maximum 12 hours per request. The front desk only lets the move through within this schedule.",
  "Se avisa a la portería. El paz y salvo se vuelve a comprobar ahora.": "The front desk is notified. The clearance certificate is checked again now.", "Se avisa a la portería.": "The front desk is notified.", "Ya hay otro trasteo en ese horario": "There is already another move at that time",
  "¿Aprobar el trasteo?": "Approve the move?", "Sí, aprobar": "Yes, approve", "Trasteo aprobado. Portería ya fue avisada.": "Move approved. The front desk has been notified.", "Rechazar la solicitud": "Reject the request",
  "Explícale al residente por qué no se aprueba.": "Explain to the resident why it is not approved.", "Solicitud rechazada": "Request rejected", "¿Cancelar el trasteo?": "Cancel the move?", "Ya estaba aprobado: se le avisa a la portería.": "It was already approved: the front desk is notified.",
  "Se retira la solicitud.": "The request is withdrawn.", "Trasteo cancelado": "Move cancelled", "Sí, iniciar": "Yes, start", "Inicio registrado": "Start recorded", "Autorizar salida": "Authorize move out", "Autorizar entrada": "Authorize move in",
  "¿Terminó el trasteo?": "Did the move finish?", "Se registra como completado.": "It is recorded as completed.", "Sí, terminó": "Yes, it finished", "Trasteo completado": "Move completed", "Registrar fin": "Record end",
  "Sin empresa ni placa registradas": "No company or license plate recorded", "Motivo": "Reason", "Trasteos de hoy": "Today's moves", "Próximos 7 días": "Next 7 days", "Solicitudes abiertas": "Open requests", "No hay trasteos autorizados": "There are no authorized moves",
  "No hay trasteos en esta lista": "There are no moves in this list", "Aún no has solicitado trasteos": "You have not requested any moves yet", "Cuando la administración apruebe uno, te llega un aviso y aparece aquí.": "When the administration approves one, you get a notice and it appears here.",
  "Las solicitudes de los residentes aparecen aquí.": "Residents' requests appear here.", "Pide uno con «Solicitar trasteo».": "Request one with “Request a move”.", "Trasteos aprobados por la administración. Verifica el horario y el paz y salvo antes de dejar pasar.": "Moves approved by the administration. Check the schedule and the clearance certificate before letting them through.",
  "Aprueba o rechaza las solicitudes. En las salidas el paz y salvo se comprueba solo.": "Approve or reject the requests. For move-outs the clearance certificate is checked automatically.", "Solicita la entrada o salida de tu trasteo. La portería recibe el aviso cuando se aprueba.": "Request your move in or move out. The front desk is notified when it is approved.", "Solicitar trasteo": "Request a move",
};

// ---------- Votaciones ----------
const GESTION_4 = {
  "Me abstengo": "I abstain", "Quitar opción": "Remove option", "Agregar opción": "Add option", "Quién vota": "Who votes", "Un voto por apartamento": "One vote per apartment", "Un voto por persona": "One vote per person",
  "Revisando los coeficientes…": "Checking the coefficients…", "Publicar votación": "Publish vote", "Nueva votación": "New vote", "Escribe la pregunta o el título.": "Write the question or title.", "Agrega al menos dos opciones.": "Add at least two options.",
  "Indica cuándo cierra la votación.": "Enter when the vote closes.", "Votación publicada. Los residentes ya recibieron el aviso.": "Vote published. Residents have been notified.", "Pregunta o título": "Question or title", "Opciones": "Options", "Cierra el": "Closes on",
  "Mostrar resultados mientras se vota": "Show results while voting", "Solo residentes al día con la administración": "Only residents up to date with the administration", "Para decisiones de asamblea.": "For assembly decisions.",
  "Cada apartamento vota con su porcentaje y se calcula el quórum. Cuenta un voto por apartamento.": "Each apartment votes with its percentage and the quorum is calculated. One vote per apartment counts.",
  "El voto es secreto: ni la administración puede ver qué votó cada persona.": "The vote is secret: not even the administration can see how each person voted.", "Nadie.": "No one.", "Ya votaron": "Already voted", "Faltan por votar": "Yet to vote",
  "Solo se muestra quién votó, nunca qué votó.": "Only who voted is shown, never what they voted.", "Elige tu opción": "Choose your option", "Resultados en vivo": "Live results", "Tu voto quedó registrado.": "Your vote was recorded.",
  "Tu voto quedó registrado. Los resultados se publican al cerrar.": "Your vote was recorded. Results are published when it closes.", "Elige una opción.": "Choose an option.", "¿Confirmas tu voto?": "Confirm your vote?", "Sí, votar": "Yes, vote",
  "Voto registrado. ¡Gracias por participar!": "Vote recorded. Thanks for taking part!", "Votar": "Vote", "¿Cerrar la votación ahora?": "Close the vote now?", "Se publican los resultados y se avisa a los residentes.": "The results are published and residents are notified.",
  "Votación cerrada": "Vote closed", "Cerrar ahora": "Close now", "¿Anular la votación?": "Void the vote?", "No se publicarán resultados. Queda en la auditoría.": "No results will be published. It stays in the audit log.", "Votación anulada": "Vote voided",
  " · solo residentes al día": " · only residents up to date", "Quién votó": "Who voted", "Votaciones abiertas": "Open votes", "Por votar": "To vote", "Aún no hay votaciones": "No votes yet", "Crea la primera con «Nueva votación».": "Create the first one with “New vote”.",
  "Cuando la administración abra una consulta, la verás aquí.": "When the administration opens a poll, you will see it here.", "Participa en las decisiones del conjunto. Tu voto es secreto.": "Take part in the complex's decisions. Your vote is secret.",
};

// ---------- Indicadores, auditoría, historial, escáner, QR, importar, cámara y mensajes de conexión ----------
const GESTION_5 = {
  "El teléfono cerró la app un momento al abrir la cámara. Tu sesión sigue activa: toma la foto de nuevo.": "The phone closed the app for a moment when opening the camera. Your session is still active: take the photo again.",
  "No pudimos procesar la foto. Intenta de nuevo.": "We could not process the photo. Try again.", "Agregar foto": "Add photo", "Toma una foto o elígela de tu galería": "Take a photo or pick one from your gallery",
  "La cámara está bloqueada. Permítela en el navegador o elige una foto de la galería.": "The camera is blocked. Allow it in the browser or pick a photo from the gallery.", "No pudimos abrir la cámara. Elige una foto de la galería.": "We could not open the camera. Pick a photo from the gallery.",
  "No pudimos capturar la foto. Intenta de nuevo.": "We could not capture the photo. Try again.", "Capturar": "Capture", "Tomar foto": "Take photo", "Galería": "Gallery", "Vista previa de la foto": "Photo preview", "Otra foto": "Another photo", "Recuperamos la foto que habías tomado.": "We recovered the photo you had taken.",
  "El registro guardado no es válido.": "The saved record is not valid.", "El registro no es válido.": "The record is not valid.", "El servidor no aceptó el registro.": "The server did not accept the record.", "Sin conexión con el servidor. Revisa tu internet.": "No connection to the server. Check your internet.",
  "Todo": "All", "Reserva": "Reservation", "Daño": "Damage report", "Anuncio": "Announcement", "Visitante": "Visitor", "Emergencia": "Emergency", "Documento": "Document", "Reporte": "Report", "Reportes": "Reports", "Ver más": "See more",
  "Cuando alguien haga cambios importantes aparecerán aquí.": "When someone makes important changes they will appear here.", "Quién hizo qué y cuándo: un respaldo para la administración ante cualquier reclamo.": "Who did what and when: a backup for the administration in case of any claim.", "Auditoría exportada a Excel.": "Audit log exported to Excel.",
  "No se pudo cargar el lector de QR.": "Could not load the QR reader.", "Sin conexión": "Offline", "Activar cámara": "Turn on camera", "Este celular no permite encender la linterna desde la app.": "This phone does not allow turning on the flashlight from the app.",
  "Este equipo no tiene cámara. Escribe el código en el campo de abajo.": "This device has no camera. Type the code in the field below.", "Otra app está usando la cámara. Ciérrala e inténtalo de nuevo.": "Another app is using the camera. Close it and try again.", "No se pudo abrir la cámara.": "Could not open the camera.",
  "Apagar cámara": "Turn off camera", "Linterna": "Flashlight", "PIN de 6 dígitos o código": "6-digit PIN or code", "Validar código": "Validate code", "Sin escaneos todavía": "No scans yet", "Aquí verás los últimos códigos leídos.": "Here you will see the latest scanned codes.", "Últimos escaneos": "Latest scans",
  "En el conjunto": "In the complex", "Permanencia": "Time inside", "Sin movimientos": "No movements", "No hay registros con estos filtros.": "There are no records with these filters.", "Anterior": "Previous", "Siguiente": "Next", "Salido": "Left", "Salieron": "Left", "Historial exportado. Ábrelo con Excel.": "History exported. Open it with Excel.",
  "Censo de residentes": "Resident census", "Súbela y revisa la vista previa: verás cuántas cuentas se crean y qué filas tienen errores.": "Upload it and check the preview: you will see how many accounts are created and which rows have errors.",
  "Al importar, descarga las claves temporales y entrégalas a cada residente. Deberán cambiarlas al ingresar.": "When importing, download the temporary passwords and give them to each resident. They must change them when signing in.", "Cartera mensual": "Monthly accounts",
  "Súbela y revisa la vista previa: verás quién entra o sale de mora y qué filas no se reconocen.": "Upload it and check the preview: you will see who becomes or stops being overdue and which rows are not recognized.", "Los apartamentos que no estén en el archivo no se tocan.": "Apartments that are not in the file are left untouched.",
  "Actualiza": "Updates", "Sin cambios": "No changes", "Error": "Error", "No hay filas válidas para importar.": "There are no valid rows to import.", "¿Importar ahora?": "Import now?", "Sí, importar": "Yes, import", "Importación terminada.": "Import finished.",
  "Descargar plantilla": "Download template", "Cambiar archivo": "Change file", "Elegir archivo": "Choose file", "Revisar archivo": "Review file", "Fila": "Row", "Resultado": "Result", "Persona": "Person", "Vista previa": "Preview", "Filas leídas": "Rows read",
  "Cuentas nuevas": "New accounts", "Saldos a actualizar": "Balances to update", "A actualizar": "To update", "Con errores": "With errors", "Errores": "Errors", "Cambios": "Changes", "Nada en este filtro": "Nothing in this filter", "Cambia el filtro para ver las demás filas.": "Change the filter to see the other rows.",
  "Importar ahora": "Import now", "Importación terminada": "Import finished", "Claves temporales: se muestran UNA sola vez.": "Temporary passwords: shown only ONCE.",
  "Descárgalas ahora y entrégalas a cada residente de forma privada. Cada persona debe cambiar su clave al ingresar. Borra el archivo cuando termines.": "Download them now and give them to each resident privately. Each person must change their password when signing in. Delete the file when you are done.",
  "¿Ocultar las claves?": "Hide the passwords?", "Sí, ocultar": "Yes, hide", "Ya las descargué, ocultar": "I downloaded them, hide", "Clave": "Password", "Ver usuarios": "View users", "Ver cartera": "View accounts", "Importar otro archivo": "Import another file",
  "Cargar datos desde Excel": "Import data from Excel", "Sube el censo de apartamentos o la cartera del mes sin digitar uno por uno.": "Upload the apartment census or the month's accounts without typing them one by one.",
  "Sin respuestas aún": "No replies yet", "Cartera al día": "Accounts up to date", "Saldo total pendiente": "Total outstanding balance", "Respuesta promedio PQRS": "Average request response time", "al día": "up to date", "Zonas más reservadas": "Most reserved areas",
  "Aún no hay reservas aprobadas en este período.": "There are no approved reservations in this period yet.", "Flujo de visitantes por hora": "Visitor flow per hour", "Aún no hay ingresos registrados en este período.": "There are no entries recorded in this period yet.", "Promedio de respuesta": "Average response time",
  "Abiertas ahora": "Open now", "Ver PQRS": "View requests", "Pendientes de hoy": "Pending today", "Lo que está esperando una acción": "What is waiting for action", "Indicadores actualizados.": "Indicators updated.", "Actualizar ahora": "Refresh now", "Cómo va el conjunto de un vistazo.": "How the complex is doing at a glance.",
  "2 días": "2 days", "3 días": "3 days", "No se pudo cargar el QR": "Could not load the QR", "Intenta de nuevo.": "Try again.", "Imagen descargada. Envíala por WhatsApp o donde prefieras.": "Image downloaded. Send it by WhatsApp or wherever you prefer.", "¿Renovar tu carnet?": "Renew your ID card?",
  "Tu QR actual dejará de funcionar de inmediato y se generará uno nuevo.": "Your current QR will stop working immediately and a new one will be generated.", "Sí, renovar": "Yes, renew", "Carnet renovado": "ID card renewed", "Renovar código": "Renew code", "Cómo usarlo": "How to use it",
  "Abre esta pantalla y muéstrasela al guardia cuando te lo pida.": "Open this screen and show it to the guard when they ask.", "El guardia lo escanea y confirma que eres quien dices ser.": "The guard scans it and confirms you are who you say you are.",
  "El QR no contiene tus datos: solo un código secreto que la portería valida.": "The QR does not contain your data: only a secret code that the front desk validates.", "Si perdiste el celular o compartiste el QR por error, renueva el código.": "If you lost your phone or shared the QR by mistake, renew the code.",
  "Tu pase de ingreso": "Your entry pass", "Enlace copiado. Pégalo en WhatsApp o donde prefieras.": "Link copied. Paste it in WhatsApp or wherever you prefer.", "No se pudo copiar. Mantén presionado el enlace para copiarlo.": "Could not copy. Press and hold the link to copy it.",
  "Compartir enlace": "Share link", "Copiar enlace": "Copy link", "Enviar imagen": "Send image", "El enlace le muestra a tu visita su QR, el PIN y cómo llegar, y le deja avisarte cuando va en camino o llega.": "The link shows your visitor their QR, the PIN and how to get there, and lets them tell you when they are on the way or arrive.",
  "Está dentro del conjunto": "Is inside the complex", "Ver QR": "View QR", "¿Revocar este pase?": "Revoke this pass?", "Sí, revocar": "Yes, revoke", "Pase revocado": "Pass revoked", "Revocar": "Revoke", "Aún no tienes pases": "You have no passes yet",
  "Crea uno cuando esperes una visita con vehículo.": "Create one when you expect a visitor with a vehicle.", "Crear pase": "Create pass", "Nuevo pase de visitante": "New visitor pass", "Escribe el nombre del visitante.": "Write the visitor's name.", "Nombre del visitante": "Visitor's name",
  "Placa del vehículo": "Vehicle license plate", "Puede ingresar durante": "Can enter during", "Invita a alguien sin llamar a portería: le envías el QR y entra con su placa registrada.": "Invite someone without calling the front desk: you send them the QR and they enter with their registered plate.",
  "Nuevo pase": "New pass", "Pases con vehículo": "Passes with vehicle", "Tu identificación digital y los pases de un solo uso para visitas con vehículo. Para personas frecuentes usa Visitantes.": "Your digital ID and single-use passes for visitors with a vehicle. For frequent visitors use Visitors.",
  "Nadie dentro": "No one inside", "No hay visitantes a pie en el conjunto.": "There are no pedestrian visitors in the complex.", "Autorización vencida": "Authorization expired", "No está autorizado": "Not authorized",
  "Ningún residente ha autorizado a esta persona. Llama al apartamento antes de dejarla pasar.": "No resident has authorized this person. Call the apartment before letting them in.", "Aquí quedan los ingresos de visitantes a pie.": "Entries of pedestrian visitors are kept here.",
  "Nombre o documento": "Name or document", "Verificar visitante": "Verify visitor", "Escribe al menos 3 caracteres. Si no aparece, nadie lo autorizó.": "Write at least 3 characters. If it does not appear, no one authorized them.", "Últimos movimientos": "Latest movements", "Ingresos exportados a Excel.": "Entries exported to Excel.",
};

// ---------- Errores del servidor, avisos push, clave, calendario, comercio local y pasarela de pagos ----------
const GESTION_6 = {
  "El archivo es demasiado grande.": "The file is too large.", "Demasiados intentos. Espera un momento e inténtalo de nuevo.": "Too many attempts. Wait a moment and try again.", "Algo falló en el servidor. Intenta de nuevo.": "Something failed on the server. Try again.",
  "No se pudo completar la acción.": "The action could not be completed.", "mié": "Wed", "sáb": "Sat", "portería": "front desk",
  "reservas, cartera, cartelera, votaciones y la gestión del conjunto": "reservations, accounts, notice board, votes and managing the complex", "reservas, paquetes, visitas, eventos y más": "reservations, packages, visitors, events and more",
  "reservas, pagos, paquetes, visitas, votaciones, eventos y más": "reservations, payments, packages, visitors, votes, events and more", "vehículos, pases QR, visitantes a pie, paquetes y trasteos": "vehicles, QR passes, pedestrian visitors, packages and moves",
  "En iPhone, primero instala la app: toca Compartir y luego «Agregar a inicio». Después podrás activar los avisos.": "On iPhone, install the app first: tap Share and then “Add to Home Screen”. Then you can turn on notifications.",
  "Este navegador no permite avisos en el celular.": "This browser does not allow notifications on the phone.", "No pudimos consultar el estado. Revisa tu conexión.": "We could not check the status. Check your connection.",
  "El administrador aún no configuró los avisos en el servidor.": "The administrator has not set up notifications on the server yet.", "Recibirás avisos de paquetes, votaciones, reservas y comunicados aunque la app esté cerrada.": "You will receive notices about packages, votes, reservations and announcements even when the app is closed.",
  "Actívalos para enterarte al instante de paquetes, votaciones y comunicados.": "Turn them on to hear instantly about packages, votes and announcements.", "Los avisos no están configurados en el servidor.": "Notifications are not set up on the server.", "No diste permiso para recibir avisos.": "You did not allow notifications.",
  "Mes anterior": "Previous month", "Mes siguiente": "Next month", "ya pasó": "already passed", "alguien ya lo pidió, aún sin aprobar": "someone already requested it, not approved yet", "No pudimos ver la disponibilidad. Intenta de nuevo.": "We could not check availability. Try again.",
  "Libre": "Free", "Ocupado": "Busy", "Alguien ya lo pidió": "Someone already requested it",
  "Contraseña actual": "Current password", "Repite la nueva contraseña": "Repeat the new password", "Guardar contraseña": "Save password", "Crea tu contraseña": "Create your password", "La nueva contraseña debe tener al menos 8 caracteres.": "The new password must be at least 8 characters long.",
  "Las contraseñas nuevas no coinciden.": "The new passwords do not match.", "Contraseña actualizada": "Password updated", "La administración restableció tu acceso. Escribe la clave temporal que te dieron y elige una propia.": "The administration reset your access. Enter the temporary password they gave you and choose your own.",
  "Comida": "Food", "Belleza": "Beauty", "Hogar": "Home", "Servicios": "Services", "Mascotas": "Pets", "Educacion": "Education", "Educación": "Education", "Escribir por WhatsApp": "Message on WhatsApp", "Aún no hay negocios": "No businesses yet",
  "Prueba con otra categoría o palabra.": "Try another category or word.", "Cuando un vecino publique su negocio, lo verás aquí.": "When a neighbor publishes their business, you will see it here.", "Buscar negocio o producto": "Search business or product", "Mensual": "Monthly", "Plan": "Plan",
  "Crear anuncio": "Create ad", "Publica tu negocio": "Publish your business", "Escribe el nombre de tu negocio.": "Write your business name.", "El WhatsApp debe ser un celular de 10 dígitos que empiece por 3.": "The WhatsApp number must be a 10-digit mobile number starting with 3.",
  "Anuncio creado. Falta el pago para activarlo.": "Ad created. Payment is still needed to activate it.", "Nombre del negocio": "Business name", "Ej. Desde $6.000": "E.g. From $6,000", "Título del anuncio": "Ad title", "WhatsApp de contacto": "Contact WhatsApp",
  "Celular de 10 dígitos, sin +57": "10-digit mobile number, without +57", "Elige tu plan": "Choose your plan", "Informar pago": "Report payment", "Informar mi pago": "Report my payment", "Escribe el número o detalle del comprobante.": "Write the receipt number or details.",
  "Pago informado. El administrador lo revisará.": "Payment reported. The administrator will review it.", "Comprobante o referencia": "Receipt or reference", "Renovar anuncio": "Renew ad", "Listo: ahora falta el pago.": "Done: now the payment is needed.", "Renovar": "Renew",
  "En revision": "Under review", "El administrador está confirmando tu pago": "The administrator is confirming your payment", "Ya pagué": "I already paid", "Tus vecinos verán tu negocio en el directorio mientras tu plan esté vigente.": "Your neighbors will see your business in the directory while your plan is valid.",
  "Publicar mi negocio": "Publish my business", "Aún no has publicado": "You have not published anything yet", "Anuncia tu comida, servicio o producto a todo el conjunto.": "Advertise your food, service or product to the whole complex.", "Por revisar": "To review", "Sin pagar": "Unpaid",
  "Vencidos": "Expired", "Rechazados": "Rejected", "Rechazar anuncio": "Reject ad", "Anuncio rechazado": "Ad rejected", "Pago confirmado: anuncio activo": "Payment confirmed: ad active", "Confirmar pago": "Confirm payment",
  "Se retira del directorio y no se puede deshacer.": "It is removed from the directory and cannot be undone.", "No hay anuncios en este estado.": "There are no ads in this status.", "Ingresos confirmados": "Confirmed income", "Anuncios activos": "Active ads",
  "Contactos generados": "Contacts generated", "Directorio": "Directory", "Mis anuncios": "My ads", "Gestión": "Management", "Los negocios de tus vecinos: comida, servicios y más, a un toque de WhatsApp.": "Your neighbors' businesses: food, services and more, one WhatsApp tap away.",
  "PSE": "PSE", "Débito desde tu cuenta bancaria": "Debit from your bank account", "Tarjeta": "Card", "Crédito o débito": "Credit or debit", "Nequi": "Nequi", "Aprueba desde tu celular": "Approve from your phone", "Una que aprueba": "One that approves", "Una que rechaza": "One that declines",
  "Una que queda pendiente": "One that stays pending", "Aprueba": "Approves", "Rechaza": "Declines", "Queda pendiente": "Stays pending", "MODO DE PRUEBAS": "TEST MODE", "· No se cobra dinero real. Así se verá el pago cuando conectemos Wompi o PSE.": "· No real money is charged. This is how the payment will look when we connect Wompi or PSE.",
  "Total a pagar": "Total to pay", "Elige cómo quieres pagar": "Choose how you want to pay", "Método de pago": "Payment method", "Banco": "Bank", "Tipo de persona": "Type of person", "Persona natural": "Individual", "Persona jurídica": "Legal entity",
  "Tipo de documento": "Document type", "Cédula de ciudadanía": "National ID card", "Cédula de extranjería": "Foreigner ID card", "NIT": "Tax ID (NIT)", "Número de documento": "Document number", "Los datos del documento son de práctica: no se envían ni se guardan.": "The document details are for practice: they are not sent or saved.",
  "Número de la tarjeta": "Card number", "CVC": "CVC", "Nombre en la tarjeta": "Name on the card", "TITULAR DE PRUEBA": "TEST CARDHOLDER", "Tarjetas de prueba:": "Test cards:", "Solo los 4 últimos dígitos viajan al servidor. El resto se borra al cerrar esta ventana.": "Only the last 4 digits travel to the server. The rest is erased when this window closes.",
  "Escribe el número completo de la tarjeta.": "Write the full card number.", "La fecha de vencimiento debe ser MM/AA.": "The expiry date must be MM/YY.", "El CVC tiene 3 o 4 números.": "The CVC has 3 or 4 digits.", "Escribe el nombre que aparece en la tarjeta.": "Write the name shown on the card.",
  "Celular de tu cuenta Nequi": "Phone of your Nequi account", "Números de prueba:": "Test numbers:", "En la pasarela real te llegaría una notificación a la app de Nequi para aprobar el pago.": "On the real gateway you would get a notification in the Nequi app to approve the payment.",
  "El celular debe tener 10 números y empezar por 3.": "The phone must have 10 digits and start with 3.", "Cambiar método": "Change method", "Procesando tu pago…": "Processing your payment…", "No cierres esta ventana.": "Do not close this window.", "Esperando la confirmación…": "Waiting for confirmation…",
  "Tu entidad está validando el pago.": "Your bank is validating the payment.", "Esto suele tardar unos segundos.": "This usually takes a few seconds.", "Pago aprobado": "Payment approved", "Pago rechazado": "Payment declined", "Pago en validación": "Payment being validated", "El tiempo se agotó": "Time ran out",
  "Descargar comprobante": "Download receipt", "Expirado": "Expired", "Tu apartamento quedó al día.": "Your apartment is now up to date.", "No se descontó nada de tu saldo.": "Nothing was deducted from your balance.",
  "Sigue en validación. Cuando se confirme, el pago aparecerá en Mis pagos.": "Still being validated. When confirmed, the payment will appear in My payments.", "Referencia": "Reference", "Método": "Method", "Valor": "Amount", "Esto fue una prueba: no se movió dinero real.": "This was a test: no real money moved.",
};

export const PATRONES = [
  [/^Bienvenido al apartamento (.+)\.$/, "Welcome to apartment $1."], [/^Bienvenido a (.+)\.$/, "Welcome to $1."],
  [/^Tienes (\d+) votación\(es\) por responder$/, "You have $1 vote(s) to answer"], [/^Tienes 1 votación por votar$/, "You have 1 vote to cast"], [/^Tienes (\d+) votaciones por votar$/, "You have $1 votes to cast"],
  [/^Tienes 1 paquete en portería$/, "You have 1 package at the front desk"], [/^Tienes (\d+) paquetes en portería$/, "You have $1 packages at the front desk"],
  [/^Vence en (\d+) día\(s\)$/, "Expires in $1 day(s)"], [/^Acceso hasta el (.+)$/, "Access until $1"],
  [/^Foto del reporte: (.+)$/, "Report photo: $1"], [/^Evidencia · (.+)$/, "Evidence · $1"], [/^Sirve hasta (.+)$/, "Valid until $1"], [/^Creado (.+)$/, "Created $1"],
  [/^Residente #(\d+)$/, "Resident #$1"], [/^Elegiste: (.+) a las (.+)$/, "You chose: $1 at $2"], [/^Solicitud radicada: (.+)$/, "Request filed: $1"],
  [/^Paz y salvo (.+) generado\. Tiene un QR para verificarlo\.$/, "Clearance certificate $1 generated. It has a QR code to verify it."], [/ · válido hasta /, " · valid until "],
  [/^Todo · (.+)$/, "All · $1"], [/^Cuota mensual: (.+)$/, "Monthly fee: $1"], [/^Saldo después: (.+)$/, "Balance after: $1"],
  [/^El valor no puede superar tu saldo \((.+)\)\.$/, "The amount cannot exceed your balance ($1)."], [/^No puede superar el saldo \((.+)\)\.$/, "It cannot exceed the balance ($1)."],
  [/^Estado de cuenta de (.+) en PDF$/, "Account statement for $1 (PDF)"], [/^Pago de (.+)$/, "Payment from $1"], [/^Saldo de (.+)$/, "Balance of $1"],
  [/^Paquete para (.+)$/, "Package for $1"], [/^Correspondencia para (.+)$/, "Mail for $1"], [/^Domicilio para (.+)$/, "Delivery for $1"], [/^Entrega de paquete para (.+)$/, "Package delivery for $1"],
  [/^Registrado para (.+)$/, "Recorded for $1"], [/^Déjalo vacío si lo recoge (.+)\. Si es otra persona, escribe su nombre\.$/, "Leave it empty if $1 picks it up. If it is someone else, write their name."],
  [/^Llegó /, "Arrived "], [/^Entregado a (.+) · (.+)$/, "Delivered to $1 · $2"], [/^Salida de (.+)$/, "Exit of $1"], [/^Salida registrada: (.+)$/, "Exit recorded: $1"], [/^Ingresó /, "Entered "],
  [/^Se muestran (\d+) de (\d+)\. El detalle completo está en la sección\.$/, "Showing $1 of $2. The full detail is in the section."], [/^1 registro$/, "1 record"], [/^(\d+) registros$/, "$1 records"],
  [/^(\d+) sin enviar$/, "$1 unsent"], [/^Chat con (.+)$/, "Chat with $1"], [/^Abrir chat con (.+)$/, "Open chat with $1"], [/^Pregúntale a (.+)$/, "Ask $1"],
  [/^Escribe tu pregunta para (.+)$/, "Type your question for $1"], [/^(.+) está escribiendo$/, "$1 is typing"],
  [/^(.+) puede equivocarse\. No escribas cédulas, teléfonos ni claves\.$/, "$1 can make mistakes. Do not write ID numbers, phone numbers or passwords."],
  [/^· (\d+) mensajes con IA hoy$/, "· $1 AI messages today"], [/^Modo básico · (.+)$/, "Basic mode · $1"],
  [/^Notificaciones: /, "Notifications: "], [/(\d+) sin leer/, "$1 unread"], [/(\d+) por gestionar/, "$1 to handle"],
  [/^Todas quedaron leídas\. Te queda 1 aviso por gestionar\.$/, "All marked as read. You have 1 notice left to handle."], [/^Todas quedaron leídas\. Te quedan (\d+) avisos por gestionar\.$/, "All marked as read. You have $1 notices left to handle."],
  [/^Tienes (\d+) avisos? por gestionar$/, "You have $1 notice(s) to handle"],
];

export const EXACTOS = {
  ...ESTRUCTURA, ...LOGIN, ...NOTIFICACIONES, ...RESUMEN, ...DANIOS, ...CHAT, ...RESERVAS, ...PQRS, ...CARTERA, ...PAQUETES, ...ANUNCIOS, ...VISITAS, ...PORTERIA, ...AJUSTES, ...GESTION_1, ...GESTION_2, ...GESTION_3, ...GESTION_4, ...GESTION_5, ...GESTION_6,
  "Tema claro · clic para cambiar": "Light theme · click to change", "Tema oscuro · clic para cambiar": "Dark theme · click to change",
  "Tema claro. Cambiar tema": "Light theme. Change theme", "Tema oscuro. Cambiar tema": "Dark theme. Change theme",
};
